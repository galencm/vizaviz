# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2018, Galen Curwen-McAdams

def keybindings():
    actions = {}
    # app always handled
    actions["app"] = {}
    actions["app"]["app_exit"] = [["c"], ["ctrl"]]
    actions["app"]["tab_next"] = [["left"], ["ctrl"]]
    actions["app"]["tab_previous"] = [["right"], ["ctrl"]]
    actions["app"]["ingest"] = [["i"], ["ctrl"]]
    # tabs have different actions / bindings
    # handled if tab is currently active / visible
    # maps
    actions["maps"] = {}
    actions["maps"]["map_next"] = [["tab"], []]
    actions["maps"]["mark_next"] = [["left"], ["shift"]]
    actions["maps"]["zoom_in"] = [["up"], ["shift"]]
    actions["maps"]["zoom_out"] = [["down"], ["shift"]]
    actions["maps"]["pan_up"] = [["up", "w"], []]
    actions["maps"]["pan_down"] = [["down", "a"], []]
    actions["maps"]["pan_left"] = [["left", "s"], []]
    actions["maps"]["pan_right"] = [["right", "d"], []]
    actions["maps"]["mark_view"] = [["space"], []]
    # loops
    actions["loops"] = {}
    actions["loops"]["viewgrid_rows_increase"] = [[],[]]
    actions["loops"]["viewgrid_rows_decrease"] = [[],[]]
    actions["loops"]["viewgrid_columns_increase"] = [[],[]]
    actions["loops"]["viewgrid_columns_decrease"] = [[],[]]
    actions["loops"]["viewgrid_loop_resolution_next"] = [[],[]]
    actions["loops"]["viewgrid_loop_resolution_previous"] = [[],[]]
    actions["loops"]["viewgrid_view_increment_increase"] = [[],[]]
    actions["loops"]["viewgrid_view_increment_decrease"] = [[],[]]
    actions["loops"]["viewgrid_scroll_up"] = [["up"],[]]
    actions["loops"]["viewgrid_scroll_down"] = [["down"],[]]
    actions["loops"]["viewgrid_jump_up"] = [[],[]]
    actions["loops"]["viewgrid_jump_down"] = [[],[]]
    actions["loops"]["cell_height_increase"] = [[],[]]
    actions["loops"]["cell_height_decrease"] = [[],[]]
    actions["loops"]["cell_width_increase"] = [[],[]]
    actions["loops"]["cell_width_decrease"] = [[],[]]
    actions["loops"]["cell_size_increase"] = [[],[]]
    actions["loops"]["cell_size_decrease"] = [[],[]]
    actions["loops"]["columns_increase"] = [[],[]]
    actions["loops"]["columns_decrease"] = [[],[]]
    actions["loops"]["increment_next"] = [[],[]]
    actions["loops"]["increment_previous"] = [[],[]]
    actions["loops"]["loop_expand"] = [[],[]]
    actions["loops"]["loop_contract"] = [[],[]]
    actions["loops"]["loop_expand_start"] = [[],[]]
    actions["loops"]["loop_contract_start"] = [[],[]]
    actions["loops"]["loop_expand_end"] = [[],[]]
    actions["loops"]["loop_contract_end"] = [[],[]]
    # -ward moves entire loop one looplength
    actions["loops"]["loop_jump_leftward"] = [[],[]]
    actions["loops"]["loop_jump_rightward"] = [[],[]]
    # move up/down a row as determined by # columns
    actions["loops"]["loop_jump_upward"] = [[],[]]
    actions["loops"]["loop_jump_downward"] = [[],[]]
    actions["loops"]["loop_next"] = [[],[]]
    actions["loops"]["loop_previous"] = [[],[]]
    actions["loops"]["loop_delete"] = [[],[]]
    actions["loops"]["loop_archive"] = [[],[]]
    actions["loops"]["loop_mute"] = [[],[]]
    actions["loops"]["loop_tag"] = [[],[]]
    actions["loops"]["loop_annotate"] = [[],[]]
    # loops selection
    actions["loops"]["loops_select_open_next"] = [[],[]]
    actions["loops"]["loops_select_open_previous"] = [[],[]]
    actions["loops"]["loops_select_next"] = [[],[]]
    actions["loops"]["loops_select_next"] = [[],[]]

    return actions
