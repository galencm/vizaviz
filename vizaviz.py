# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2018, Galen Curwen-McAdams

import argparse
import pathlib
import os
import subprocess
import io
import uuid
import json
from urllib.parse import urlparse
import functools
import hashlib
import time
import trio
import psutil
import redis
from xdg import (XDG_CACHE_HOME, XDG_CONFIG_HOME, XDG_DATA_HOME)
import numpy as np
from PIL import Image, ImageDraw, ImageShow
import processors_audio

# set to get entire numpy array as string
# when using str(array)
np.set_printoptions(threshold=np.inf)

q = trio.Queue(1)
COLORMAP_RESOLUTIONS = [1, 4, 8, 16, 32]
SERVER_ID = "vzz"
VIZAVIZ_DATA_DIR = pathlib.PurePath(XDG_DATA_HOME, "vizaviz")
VIZAVIZ_CONFIG_DIR = pathlib.PurePath(XDG_CONFIG_HOME, "vizaviz")
VIZAVIZ_TEMP_DIR = pathlib.PurePath("/tmp")
VIZAVIZ_FIFO_DIR = pathlib.PurePath("/tmp")

# use feh instead of display for pillow .show()
class FehViewer(ImageShow.UnixViewer):
    def show_file(self, filename, **options):
        os.system('feh {}'.format(filename))
        return 1

ImageShow.register(FehViewer, order=-1)

def despawn_loop(pid):
    print("removing pid {}".format(pid))
    process = psutil.Process(pid)
    process.terminate()

def spawn_loop(file, loop_uuid):
    fifo_uuid = pathlib.PurePath(VIZAVIZ_FIFO_DIR, loop_uuid)
    #fifo = os.mkfifo(fifo_uuid)
    p = subprocess.Popen(["mpv",
                  file,
                  "--input-ipc-server={}".format(fifo_uuid),
                  "--keep-open=yes"])
    return p.pid

def write_to_pipe(fifo_name, to_write):
    print("writing to pipe: {}".format(to_write))
    if not to_write.endswith("\n"):
        to_write += "\n"
    try:
        output = subprocess.Popen(['socat', '-', pathlib.PurePath(VIZAVIZ_FIFO_DIR, fifo_name)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        output.stdin.write(to_write.encode())
        ostdout = output.communicate()[0]
        output.stdin.close()
        return ostdout.decode()
    except:
        return ""

def loop_running(data):
    try:
        if not data['uuid'] in redis_conn.hgetall("vizaviz:{server_id}:state:running".format(server_id=SERVER_ID)).keys():
            return False
        else:
            return True
    except KeyError:
        return False

def idempotent_create_loop(name, data):
    spawn = True
    try:
        # do not try to spawn/respawn if loop is
        # archived / dormant / inactive
        if 'archive' in data['status']:
            spawn = False
    except KeyError:
        spawn = True

    if spawn:
        data['pid'] = spawn_loop(data['filename'], data['uuid'])
        redis_conn.hmset("vizaviz:{server_id}:state:running".format(server_id=SERVER_ID), { data['uuid'] : data['pid']})
        redis_conn.hmset(name, {"pid" : data['pid']})
        # use a slight delay to allow fifo to open
        # so write_pipe commands will not initially fail
        time.sleep(.75)
    return data

async def get_state(redis_conn):
    print("getting state")
    # vizaviz:state:open [list of filenames]
    # vizaviz:state:close [list of fifo ids]
    for key in redis_conn.scan_iter("vizaviz:{server_id}:loop:*".format(server_id=SERVER_ID)):
        data = redis_conn.hgetall(key)
        if not loop_running(data):
            data = idempotent_create_loop(key, data)
        try:
            pid = int(redis_conn.hget("vizaviz:{server_id}:state:running".format(server_id=SERVER_ID), data['uuid']))
            try:
                proc = psutil.Process(pid)
                print("pid: {0} status: {1}".format(pid, proc.status()))
                if proc.status() == psutil.STATUS_ZOMBIE:
                    idempotent_create_loop(key, data)
            except psutil.NoSuchProcess:
                idempotent_create_loop(key, data)
        except:
            # if pid is not successfully retrieved
            data = idempotent_create_loop(key, data)

        # check loop
        # this seems to be spiking cpu usage
        loop_start = write_to_pipe(data['uuid'], '{"command" : ["get_property","ab-loop-a"]}')
        loop_end = write_to_pipe(data['uuid'], '{"command" : ["get_property","ab-loop-b"]}')
        loop_volume = write_to_pipe(data['uuid'], '{"command" : ["get_property","volume"]}')
        
        # use loop volume to set on start
        try:

            loop_start = json.loads(loop_start)['data']
            loop_end = json.loads(loop_end)['data']
            adjusted_loop = False
            # ab-loop-a not yet set:
            # {"data":"no","error":"success"}

            # ab-loop-a set:
            # {"data":1.000000,"error":"success"}
            print("ipc loop info: ", loop_start, (loop_start != float(data['start'])))
            try:
                if loop_start != float(data['start']) and float(data['start']) >= 0:
                    write_to_pipe(data['uuid'], '{{"command" : ["set_property","ab-loop-a", {}]}}'.format(data['start']))
                    adjusted_loop = True
            except KeyError:
                pass

            try:
                if loop_end != float(data['end']) and float(data['end']) >= 0:
                    write_to_pipe(data['uuid'], '{{"command" : ["set_property","ab-loop-b", {}]}}'.format(data['end']))
            except KeyError:
                pass

            try:
                if loop_volume != str(data['volume']):
                    write_to_pipe(data['uuid'], '{{"command" : ["set_property","volume", {}]}}'.format(data['volume']))
            except KeyError:
                pass

            if adjusted_loop:
                write_to_pipe(data['uuid'], '{{ "command": ["seek",{0},"absolute"]}}'.format(data['start']))

        except Exception as ex:
            print(ex)

def audio_image_from_file(source, map_file_prefix=""):
    # 'spectrogram' should not be hardcoded
    print("generating spectrogram for {}".format(source))
    try:
        map_file = pathlib.PurePath(VIZAVIZ_DATA_DIR, 'map_image_spectrogram_{0}.jpg'.format(map_file_prefix))
        processors_audio.spectrogram_image(source, image_filename=str(map_file))
    except Exception as ex:
        print(ex)

def images_to_db(map_file=None, map_file_prefix=""):
    p = pathlib.Path(VIZAVIZ_DATA_DIR)
    image_files = list(p.glob('map_image*.jpg'))
    for file in image_files:
        #map_image_spectrogram_11111
        _, _, map_name, map_file_prefix = file.stem.split("_")
        # for now set image_name to map_name
        image_name = map_name
        image_bytes = io.BytesIO()
        with open(file, 'rb') as f:
            image_bytes = io.BytesIO(f.read())
        image_bytes.seek(0)
        redis_conn.hmset("source:{}".format(map_file_prefix), {"map:{map_name}:image:{image_name}".format(map_name=map_name, image_name=image_name) : image_bytes.getvalue()})

def frames_from_file(source, destination, frame_file_prefix=""):
    #fps=1/30'
    #1 per second
    os.makedirs(destination, exist_ok=True)
    subprocess.call(['ffmpeg',
                     '-i',
                     str(source),
                     '-vf',
                     'fps=1',
                     "{0}/{1}_{2}".format(destination, frame_file_prefix, '%08d.bmp')
                    ])
    p = pathlib.Path(destination)
    frame_files = list(p.glob('**/{}*.bmp'.format(frame_file_prefix)))
    colormap_from_frames(frame_files, frame_file_prefix)

def colormap_from_frames(sources, map_file_prefix=""):
    created_map_files = []
    for resolution in COLORMAP_RESOLUTIONS:
        map_file = pathlib.PurePath(VIZAVIZ_DATA_DIR, '{0}_{1}.npy'.format(map_file_prefix, resolution))
        created_map_files.append(map_file)
        if not os.path.isfile(map_file):
            print("creating colormap {0} for resolution: {1}".format(map_file_prefix, resolution))
            sources.sort()
            color_map = []
            for file in sources:
                color_map.append(create_map(file, resolution))

            rgb_array = np.zeros(shape=(len(sources), resolution, 3))
            for imgslice, pixel_group in enumerate(color_map):
                for res, (_, rgb) in enumerate(pixel_group):
                    for px, pixel in enumerate(rgb): 
                        rgb_array[imgslice][res][px] = pixel

            np.save(str(map_file), rgb_array)
            colormap_to_db(str(map_file), resolution, map_file_prefix)
    return created_map_files

def colormap_to_db(map_file, resolution, map_file_prefix=""):
    rgb_array = np.load(str(map_file))
    # store in redis as a flat list of numbers
    # space delimited ie 1 2 3
    #with np.printoptions(threshold=np.inf):
    str_rgb_array = str(rgb_array.flatten()).replace(".", "").replace("\n", "")[1:-1]
    # redis_conn here is used from global scope
    redis_conn.hmset("source:{}".format(map_file_prefix), {"map:rgb_map:resolution:{}".format(str(resolution)) : str_rgb_array})
    
    duration = len(rgb_array)
    redis_conn.hmset("source:{}".format(map_file_prefix), {"duration" : duration})

def create_map(source_image, num_colors):
    with Image.open(source_image) as pim:
        im = pim.convert('P', palette=Image.ADAPTIVE, colors=num_colors)
    pim.close()
    im = im.convert('RGB')
    colorlist = []
    for color in im.getcolors(64000):
        colorlist.append(color)
    im.close()
    return colorlist

def visualize_loop(start, end, duration, resolution, loop_color=None, bg_color=None, cell_width=10, cell_height=10, return_image=False, return_format="PNG"):
    width = int(duration * resolution * cell_width)
    height = int(cell_height)
    if loop_color is None:
        loop_color = (240, 240, 240, 1)
    if bg_color is None:
        bg_color = (50, 50, 50, 0)
    visualization_image = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(visualization_image)
    draw.rectangle(((int(start)), 0,
                    (int(end * cell_width * resolution), 0 + cell_height)),
                    fill=(loop_color))

    if return_image:
        image_bytes = io.BytesIO()
        visualization_image.save(image_bytes, return_format)
        visualization_image.close()
        image_bytes.seek(0)
        return image_bytes
    else:
        visualization_image.show()

async def ingest(urls, destination_directory):
    # try youtube-dl, then wget/curl for other things
    # use youtube-dl to get potential filename
    # to see if already downloaded
    # parse urls? urlparse(url).geturl()

    history_key = "vizaviz:{server_name}:history".format(server_name=SERVER_ID)
    already_ingested = redis_conn.smembers(history_key)
    for url in urls:
        valid_url = urlparse(url)
        if valid_url.scheme and  valid_url.netloc and valid_url.path:
            print("url valid: {}".format(valid_url))
            if valid_url not in already_ingested:
                filename = subprocess.check_output(["youtube-dl", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4", valid_url, "--get-filename"]).decode().strip()
                if not os.path.isfile(pathlib.PurePosixPath(destination_directory, filename)):
                    subprocess.Popen(["youtube-dl", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4", valid_url],
                                    cwd=destination_directory)
                redis_conn.sadd(history_key, valid_url)
        else:
            print("url not valid: {}".format(valid_url))
#@functools.lru_cache(maxsize=32)
def visualize_map(map_file=None, map_raw=None, cell_width=10, cell_height=10, rows=None, columns=None, resolution=None, return_image=False, return_format="PNG", reverse_image=False):
    if map_file:
        map_file = pathlib.PurePosixPath(map_file)
        # try to get resolution from filename if none provided
        if resolution is None:
            resolution = int(map_file.stem.partition("_")[-1])
        array = np.load(str(map_file))
        # array = array.flatten()
    elif map_raw:
        # must specify resolution in kwargs
        rgb_values = 3
        array = np.array(map_raw)
        # create rgb cells
        array = array.reshape((-1, rgb_values))
        # split frames
        array = np.split(array, len(array) / resolution)
        # reverse the array so that image flows bottom to
        # top instead of top to bottom
        # doing it this way to be easier for in-progress gui

    if reverse_image is True:
        array = array[::-1]

    cells = len([cell for cell in array]) * resolution

    if columns == "auto":
        columns = resolution
        width = resolution * cell_width
        height = cell_height * int(cells / columns)
    elif columns:
        width = resolution * cell_width
        height = cell_height * int(cells / columns)
    else:
        # some _32 with single row are not working?
        height = cell_height
        width = cells * cell_width

    visualization_image = Image.new("RGB", (width, height))
    x = 0
    y = 0
    columns_filled = 0
    for frame in array:
        for rgb_cell in frame:
            fill_rgb = [int(c) for c in rgb_cell]
            draw = ImageDraw.Draw(visualization_image)
            draw.rectangle(((x, y),
                            (x + cell_width, y + cell_height)),
                            fill=(*fill_rgb, 0))
            x += cell_width
            if columns_filled == columns:
                y += cell_height
                x = 0
                columns_filled = 0
            columns_filled += 1

    if return_image:
        image_bytes = io.BytesIO()
        visualization_image.save(image_bytes, return_format)
        visualization_image.close()
        image_bytes.seek(0)
        return image_bytes
    else:
        visualization_image.show()

def file_already_processed(file_hash):
    for resolution in COLORMAP_RESOLUTIONS:
        processed = pathlib.PurePath(VIZAVIZ_DATA_DIR, "{file_hash}_{resolution}.npy".format(file_hash=file_hash, resolution=resolution))
        if not os.path.isfile(processed):
            return False
        else:
            print("already processed: {}".format(processed))

    return True

async def ingest_from(check_interval=30):
    # keychanges should handle most ingest
    # but this will handle restart of server
    for key in redis_conn.scan_iter("vizaviz:*ingest".format(server_id=SERVER_ID)):
        urls = redis_conn.smembers(key)
        await ingest(urls, VIZAVIZ_SERVER_DIRS[0])

    for count in range(check_interval):
        print("source from: sleeping {}".format(count))
        await trio.sleep(1)

async def source_from(directory_name, directory_check_interval, processed_sources):
    p = pathlib.Path(directory_name)
    # include jpg, bmp -- treat as duration 0 -1
    source_files = list(p.glob('**/*.mp4'))
    for file in source_files:
        if file not in processed_sources:
            with open(file,'rb') as f:
                file_hash = hashlib.sha1(f.read()).hexdigest()
            audio_image_from_file(file, file_hash)
            images_to_db()
            if not file_hash in processed_sources.values() and not file_already_processed(file_hash):
                # if hash not found in dict, process
                # process audio image
                try:
                    frames_from_file(file, VIZAVIZ_TEMP_DIR, frame_file_prefix=file_hash)
                    processed_sources[file] = file_hash
                    redis_conn.hmset("source:{}".format(file_hash), {"filename" : file})
                    redis_conn.hmset("source:{}".format(file_hash), {"filehash" : file_hash})
                except Exception as ex:
                    print("exception while processing file: {0} {1}".format(file, ex))
            else:
                processed_sources[file] = file_hash
                redis_conn.hmset("source:{}".format(file_hash), {"filename" : file})
                redis_conn.hmset("source:{}".format(file_hash), {"filehash" : file_hash})
                # files exist...
                # check if maps are in db
                for resolution in COLORMAP_RESOLUTIONS:
                    map_file = pathlib.PurePath(VIZAVIZ_DATA_DIR, '{0}_{1}.npy'.format(file_hash, resolution))
                    if os.path.isfile(map_file):
                        colormap_to_db(map_file, resolution, file_hash)

    # sleep for interval
    for count in range(directory_check_interval):
        print("source from: sleeping {}".format(count))
        await trio.sleep(1)
    await q.put(processed_sources)

async def handle_key_events(redis_conn, q):
    pubsub = redis_conn.pubsub()
    pubsub.psubscribe("__keyspace@0__:*")
    #pubsub.psubscribe(**{'__keyspace@0__:*': event_handler})
    while True:  
        message = pubsub.get_message()
        if message:
            # print(message)
            if message["data"] == "sadd" and "ingest" in message["channel"]:
                # how to handle ingest?
                # url, tag to specify directory?
                #   servers could specify which tags to handle
                #   for example 0101 to put into dir '0101' to structure by date
                # use a sorted set and timestamps?
                key = message["channel"].replace("__keyspace@0__:","")
                urls = redis_conn.smembers(key)
                await ingest(urls, VIZAVIZ_SERVER_DIRS[0])
            if message["data"] == "del" and "loop" in message["channel"]:
                loop_key = message["channel"].replace("__keyspace@0__:","")
                loop_id = message["channel"].split(":")[4]
                #loop_server = message["channel"].split(":")[2]
                # {'type': 'pmessage', 'pattern': '__keyspace@0__:*', 'channel': '__keyspace@0__:vizaviz:foo:loop:5a5ed69c-7d4a-4c5e-b849-790f5b3dcdfd', 'data': 'del'}
                #stop the loop first
                loop_pid = int(redis_conn.hget("vizaviz:{server_id}:state:running".format(server_id=SERVER_ID), loop_id))
                # can't get pid because key already deleted by client
                #loop_pid = int(redis_conn.hget(loop_key, 'pid'))
                despawn_loop(loop_pid)
            await get_state(redis_conn)
        else:
            try:
                # for now, any message in q ends function
                q.get_nowait()
                break
            except Exception as ex:
                await trio.sleep(0.01)

async def main(directories, redis_conn):
    directory_check_interval = 10
    # path/filename : contents hash
    processed_sources = {}
    key_q = trio.Queue(1)
    try:
        while True:
            async with trio.open_nursery() as nursery:
                nursery.start_soon(handle_key_events, redis_conn, key_q)
                for directory in directories:
                    print("checking directory: {}".format(directory))
                    nursery.start_soon(source_from, directory, directory_check_interval, processed_sources)
                    nursery.start_soon(ingest_from)
                sources_from_directory = await q.get()
                processed_sources.update(sources_from_directory)
                if processed_sources:
                    redis_conn.hmset("vizaviz:{server_id}:sources".format(server_id=SERVER_ID), processed_sources)
                key_q.put_nowait("stop")
    except Exception as ex:
        # trio works with ctrl-c
        print(ex, "exiting...")

def create_xdg_dirs():
    for directory in (VIZAVIZ_DATA_DIR, VIZAVIZ_TEMP_DIR, VIZAVIZ_FIFO_DIR, VIZAVIZ_CONFIG_DIR):
        if not os.path.isdir(directory):
            print("{} does not exist, creating directory...")
            os.mkdir(directory)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir",
                        nargs='+',
                        default=["."],
                        help="directories to use/watch for sources")

    parser.add_argument("--map-resolutions",
                        nargs='+',
                        default=[],
                        type=int,
                        help="resolutions to use")

    parser.add_argument("--server-name", default=None)
    parser.add_argument("--show-map", default=None)
    parser.add_argument("--show-resolution", default=None, type=int)
    parser.add_argument("--show-columns", default=None, type=int)
    parser.add_argument("--show-cell-width", default=10, type=int)
    parser.add_argument("--show-cell-height", default=10, type=int)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=6379)
    parser.add_argument("--auth", default="")
    parser.add_argument("--data-dir", default=VIZAVIZ_DATA_DIR)
    parser.add_argument("--temp-dir", default=VIZAVIZ_TEMP_DIR)
    parser.add_argument("--fifo-dir", default=VIZAVIZ_FIFO_DIR)
    parser.add_argument("--config-dir", default=VIZAVIZ_CONFIG_DIR)

    args = parser.parse_args()

    VIZAVIZ_SERVER_DIRS = args.source_dir

    if args.data_dir != VIZAVIZ_DATA_DIR:
        VIZAVIZ_DATA_DIR = args.data_dir

    if args.temp_dir != VIZAVIZ_TEMP_DIR:
        VIZAVIZ_TEMP_DIR = args.temp_dir

    if args.config_dir != VIZAVIZ_CONFIG_DIR:
        VIZAVIZ_CONFIG_DIR = args.config_dir

    if args.fifo_dir != VIZAVIZ_FIFO_DIR:
        VIZAVIZ_FIFO_DIR = args.fifo_dir

    create_xdg_dirs()

    try:
        r_ip, r_port = args.host, args.port
        # redis_conn_binary = redis.StrictRedis(host=r_ip, port=r_port)
        redis_conn = redis.StrictRedis(host=r_ip, port=r_port, decode_responses=True)
    except redis.exceptions.ConnectionError:
        pass

    if args.server_name:
        SERVER_ID = args.server_name

    if args.map_resolutions:
        COLORMAP_RESOLUTIONS = args.map_resolutions

    if args.show_map:
        visualize_map(args.show_map,
                      resolution=args.show_resolution,
                      cell_height=args.show_cell_height,
                      cell_width=args.show_cell_width,
                      columns=args.show_columns)
    else:
        trio.run(main, args.source_dir, redis_conn)