# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2018, Galen Curwen-McAdams

import io
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
matplotlib.use('Agg')
import librosa
import librosa.display

def spectrogram_image(filename, image_filename=None, return_as_bytes=True, width=2, height=2):
    time_series_array, sampling_rate = librosa.load(filename, offset=40, duration=10)
    stft_matrix = librosa.stft(time_series_array)
    rp = np.max(np.abs(stft_matrix))
    #plt.figure(figsize=(2, 2))
    fig = plt.figure(frameon=False)
    fig.set_size_inches(width, height)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    librosa.display.specshow(librosa.amplitude_to_db(stft_matrix, ref=rp), x_axis='log')
    #librosa.display.specshow(librosa.amplitude_to_db(stft_matrix, ref=rp), y_axis='log')
    if return_as_bytes is True and image_filename is None:
        image = io.BytesIO()
        plt.savefig(image ,dp=1)
        image_bytes.seek(0)
        return image
    else:
        plt.savefig(image_filename ,dp=1)
        return image_filename