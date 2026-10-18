#!/usr/bin/env python3
"""
Behringer XR16 / XR18 remote control - a single-file GUI application.
=====================================================================

What this program does
----------------------
* Complete graphical remote control for the Behringer XR16 and XR18
  (X AIR family) digital mixers.
* Talks to the mixer with the OSC (Open Sound Control) protocol over
  stateless UDP, exactly like the official "X AIR Edit" application.
* Five horizontal tabs: "MIXER" shows the channel faders (CH01 ... CH18)
  plus the Main LR fader - each strip with its own MUTE and SOLO
  buttons.  "AUX" shows the 6 Bus outputs (AUX1 ... AUX6), "FX" the 4
  FX returns (FX1 ... FX4) and "DCA" the 4 DCA masters (DCA1 ... DCA4),
  also with MUTE and SOLO buttons below every fader.  "RTA" shows the
  real-time level meter bridge of every mixer source (see below).  The
  mixer model reported by "/xinfo" is verified on every connection: an
  XR16 shows its 16 channel faders (CH17/CH18 are hidden), an XR18
  shows all 18.
* Remembers the mixer IP address in a small JSON configuration file that
  sits next to this script ("xr_remote_config.json"), so the address is
  restored the next time the application is started.
* A vertical level meter next to every fader (16 LED segments
  green / yellow / red with a peak-hold marker) shows the signal level
  of that channel, bus or FX return in real time - updated about every
  50 ms by the mixer.  DCA faders have no meter: the X AIR meter blob
  does not include DCA levels.
* The "RTA" tab is a full meter bridge driven by the same "/meters/1"
  batch (no extra subscription): tall LED bars for every input channel,
  the Main output, the 6 buses and the 4 FX returns side by side, with
  a dB scale, channel labels that follow the scribble colour and a
  falling peak readout under each bar.  CH17/CH18 hide on an XR16.
* Double-click a channel label (CH01 ... CH18) on the MIXER tab to open
  the channel editor window: input source, preamp gain, pan, noise gate
  (mode, threshold, range, attack/hold/release, key source + key filter),
  the 4-band equalizer, the compressor, all AUX 1-6 and FX 1-4 sends, the
  Main LR output (level, routing, mute) and the DCA / mute group
  assignment switches.  The window queries the live values from the
  mixer (re-asking the rare dropped UDP answer), follows every remote
  change and writes every user action back with OSC.
* Dark "live console" styling: near-black background, slate strip cards
  with hairline borders that light up on hover, an electric-blue accent,
  custom drawn faders with a graded setpoint fill, a segmented LED level
  meter and per-channel scribble colours that tint the strip's identity
  bar and fader groove.
* Errors are written to "xr_remote.log" next to this script (rotating,
  256 KB x 3 backups): every red status-bar message, unhandled
  exceptions and Tk callback crashes - each with its full traceback.
  Logging is best effort: in a read-only folder it is switched off
  instead of breaking the application.
* Listens to the mixer continuously, so any change made on the hardware
  itself (or by another controller / X AIR Edit) is mirrored in this GUI
  in real time - and vice versa.

How to run
----------
    pip install python-osc
    python xr16_xr18_remote.py

Tkinter ships with the standard Python distribution, therefore the only
third-party dependency is "python-osc".

X AIR protocol facts used by this program (Behringer remote control
protocol, firmware 1.11 and newer):
  * The mixer listens for OSC packets on UDP port 10024
    (factory default IP address: 192.168.1.1).
  * Every reply is sent back to the exact IP address AND source port the
    request came from.  For that reason this program uses ONE single UDP
    socket (created by BlockingOSCUDPServer) for both sending and
    receiving - a second socket would never see the feedback.
  * "/xinfo" (sent with no arguments) makes the mixer answer with
    IP, name, model and firmware version -> used as ping / connection
    check, as the visual connection indicator and to verify the model
    (XR16/XR18 -> number of channel faders shown).
  * Sending a message with NO arguments to any parameter address, for
    example "/ch/01/mix/fader", queries the current value; the mixer
    echoes it back.  This is how the console state is loaded: the whole
    set of faders/mutes/solos is queried right after the handshake, the
    arriving values position every fader and button in the GUI, missing
    answers are retried (UDP can drop packets), and the "Reload state"
    button repeats the load at any time.
  * "/xremote" (no arguments) must be re-sent at least every 10 seconds.
    It switches the mixer into remote mode so that it pushes *all*
    parameter changes back to this client (feedback / subscription).
  * Level meters: "/meters" with the two arguments ("/meters/1", 1)
    subscribes to the "ALL CHANNELS" meter batch - the mixer then pushes
    a binary blob to "/meters/1" about every 50 ms (an int32 count
    followed by 40 signed int16 values, little endian, 1/256 dB).  The
    subscription stops after ~10 s unless it is renewed with "/renew"
    and the same address string (done by the heartbeat together with
    "/xremote").  Index table of the 40 values: 0-15 = CH01-16 pre,
    16-17 = AUX in L/R (CH17/18), 18-25 = FX1-4 pre L/R, 26-31 =
    Bus1-6 pre, 32-35 = FX send 1-4, 36-37 = Main L/R post,
    38-39 = Monitor L/R.  No DCA levels in this blob.
  * Channel detail parameters (channel editor window): "/ch/01/gate/thr",
    "/ch/01/eq/2/g", "/ch/01/dyn/ratio", "/ch/01/mix/03/level",
    "/ch/01/config/insrc", "/ch/01/mix/pan", ...  Continuous values are
    normalised floats 0.0..1.0 mapped onto their real range either
    linearly (threshold -80..0 dB, EQ gain -15..+15 dB) or
    logarithmically (hold 0.02..2000 ms, frequency 20..20000 Hz, EQ Q
    10..0.3); switches are integers 0/1 and enumerations are integer
    indexes (dyn/ratio 0..11, EQ band type 0..5, keysrc 0..22).  The
    sends of a channel are "/ch/NN/mix/01..06/level" for AUX 1-6 and
    "/ch/NN/mix/07..10/level" for FX 1-4; the input source lives at
    "/ch/NN/config/insrc".  The DCA and mute group assignments of a
    channel are each ONE integer bitmask: "/ch/NN/grp/dca" and
    "/ch/NN/grp/mute", int 0-15, bit 0 = group 1 ... bit 3 = group 4
    (official Parameters.txt: "%0000" = 4 bits).
  * The preamp gain is the one editor value outside /ch/NN/...:
    "/headamp/NN/gain" (NN = zero padded channel number), float
    0.0..1.0 mapped linearly onto -12 ... +60 dB.  The official
    Parameters.txt prints "-12 - +20" for this address - that range
    only describes headamps 17..24, which no X AIR input exposes;
    pmaillot's XAirSetSceneParse.c (Xp_linf(-12., 72., ...)) and
    xair-api-python (lin_get(-12, 60, ...)) confirm 01..16 = -12..+60.

OSC addresses used by this application:
  Channel volume   /ch/01/mix/fader ... /ch/18/mix/fader  float 0.0 - 1.0
  Channel mute     /ch/01/mix/on     ... /ch/18/mix/on    int  0 = MUTE ON,
                                                               1 = MUTE OFF
  Main volume      /lr/mix/fader                         float 0.0 - 1.0
  Main mute        /lr/mix/on                            int  0 = MUTE ON,
                                                              1 = MUTE OFF
  AUX bus volume   /bus/1/mix/fader ... /bus/6/mix/fader float 0.0 - 1.0
  AUX bus mute     /bus/1/mix/on     ... /bus/6/mix/on   int  0 = MUTE ON,
                                                              1 = MUTE OFF
  FX return volume /rtn/1/mix/fader  ... /rtn/4/mix/fader float 0.0 - 1.0
  FX return mute   /rtn/1/mix/on     ... /rtn/4/mix/on   int  0 = MUTE ON,
                                                               1 = MUTE OFF
  DCA master volume /dca/1/fader       ... /dca/4/fader      float 0.0 - 1.0
  DCA master mute   /dca/1/on          ... /dca/4/on         int  0 = MUTE ON,
                                                                  1 = MUTE OFF
                                                                  (NOTE: no
                                                                  "/mix/"
                                                                  level on
                                                                  DCA
                                                                  addresses)
  Channel solo     /-stat/solosw/01 ... /-stat/solosw/16  int  1 = solo ON
  Aux solo switch  /-stat/solosw/17   (CH17 / CH18 share it on the X AIR)
  FX return solo   /-stat/solosw/18 ... /-stat/solosw/21  (FX 1 ... FX 4)
  AUX bus solo     /-stat/solosw/40 ... /-stat/solosw/45  (Bus 1 ... Bus 6)
  Main solo switch /-stat/solosw/50   (Main LR)
  DCA solo switch  /-stat/solosw/51 ... /-stat/solosw/54  (DCA 1 ... DCA 4)
  Scribble name    /ch/01/config/name ... /ch/18/config/name  string (<=32)
                   /lr/config/name, /bus/1/config/name ...,
                   /rtn/1/config/name ..., /dca/1/config/name ...
                   (edited by double-click)
  Scribble colour  /ch/01/config/color ... /ch/18/config/color  int 0-15
                   /lr/config/color, /bus/1/config/color ...,
                   /rtn/1/config/color ..., /dca/1/config/color ...
                   (right-click the name field)
  Preamp gain      /headamp/01/gain ... /headamp/18/gain   float 0.0 - 1.0
                   (linearly -12 ... +60 dB; NOTE: unlike the strip
                   addresses this one is NOT under /ch/NN/)
  NOTE: bus, FX-return and DCA addresses use a SINGLE digit
  ("/bus/1/...", not "/bus/01/..."; same for "/rtn/1/..." and
  "/dca/1/...").  DCA fader/mute also skip the "mix" level that
  channels/buses/returns use: "/dca/1/fader" and "/dca/1/on".
  The solosw index follows the documented scheme "0-based source id + 1":
  0-15 = CH1-16, 16 = AUX input (CH17/18), 17-20 = FX return,
  21-38 = USB, 39-44 = Bus 1-6 (-> solosw 40-45), 45-48 = FX send,
  49 = Main LR (-> solosw/50), 50-53 = DCA 1-4 (-> solosw 51-54).
  This is the same numbering the X32 uses there L/R = solosw/71.

Architecture / thread model
---------------------------
    Tkinter GUI (main thread)               OSC layer (daemon thread)
    ------------------------------------------------------------------
    MixerGUI  -- commands --------------->  OscMixer.send(...)
        ^                                      |  UDP socket
        |  queue.Queue of simple tuples        v
        +------------- events <-----------  BlockingOSCUDPServer loop

    The GUI never blocks on the network.  All socket work happens in a
    background thread; incoming messages are placed into a thread-safe
    queue that the GUI drains with Tkinter's after() timer (see
    MixerGUI._poll_events).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import logging.handlers
import math
import queue
import struct
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

# ---------------------------------------------------------------------------
# Dependency check - fail with a helpful message instead of a traceback.
# ---------------------------------------------------------------------------
try:
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_message_builder import OscMessageBuilder
    from pythonosc.osc_server import BlockingOSCUDPServer
except ImportError:  # pragma: no cover - environment dependent
    sys.exit(
        "Missing dependency 'python-osc'.\n"
        "Install it with:  pip install python-osc"
    )


# ===========================================================================
# 1. Configuration constants
# ===========================================================================

# --- Network ---------------------------------------------------------------
DEFAULT_MIXER_IP = "192.168.1.1"   # factory default of the X AIR mixers
MIXER_OSC_PORT = 10024             # X AIR series listens on UDP port 10024
NUM_CHANNELS = 18                  # CH01..CH18 (XR16 has 16 physical inputs)
NUM_BUSES = 6                      # Bus 1..6 = the AUX/monitor outputs
NUM_FX = 4                         # FX return 1..4 (the 4 effect processors)
NUM_DCAS = 4                       # DCA 1..4 (digit al control associations)
MAIN_STRIP = "lr"                  # internal key of the Main LR fader

# --- Configuration file ----------------------------------------------------
# The last mixer IP address is stored in a small JSON file next to this
# script so it can be restored on the next start of the application.
CONFIG_FILE = Path(__file__).with_name("xr_remote_config.json")

# --- Error log file --------------------------------------------------------
# Errors and warnings are appended to this file next to the script (see
# the "Error log file" section below).  It rotates before it can grow
# without limit: xr_remote.log plus at most LOG_BACKUPS older copies.
LOG_FILE = Path(__file__).with_name("xr_remote.log")
LOG_MAX_BYTES = 256_000    # start a fresh file after 256 KB of log text
LOG_BACKUPS = 3            # keep xr_remote.log.1 ... .3 as history

# --- Timing (seconds) ------------------------------------------------------
HEARTBEAT_MS = 500       # GUI timer resolution for link supervision
POLL_INTERVAL_MS = 30    # how often the GUI drains the OSC event queue
PING_INTERVAL_S = 3.0    # "/xinfo" ping while connected or connecting
XREMOTE_RENEW_S = 5.0    # renew "/xremote" (mixer drops it after ~10 s)
LINK_TIMEOUT_S = 10.0    # no reply at all for this long -> connection lost
CONNECT_TIMEOUT_S = 6.0  # no "/xinfo" answer -> mixer unreachable
STATE_LOAD_TIMEOUT_S = 2.5   # wait for the full console state after a query
STATE_LOAD_RETRIES = 2       # re-query passes for parameters that stayed quiet

# --- Layout ----------------------------------------------------------------
FADER_WIDTH = 60
FADER_HEIGHT = 280
MAX_NAME_LEN = 32           # scribble-strip name length limit

# --- Level meters ----------------------------------------------------------
# One subscription ("/meters" with the arguments "/meters/1" and 1) makes
# the mixer push the "ALL CHANNELS" meter batch to "/meters/1" about every
# 50 ms: an int32 count followed by 40 signed int16 values (1/256 dB,
# little endian).  "/renew" with the same string keeps the stream alive.
METER_SUBSCRIPTION = "/meters/1"    # reply address of the meter batch
METER_ID_ALL_CHANNELS = 1           # meter id 1 = "ALL CHANNELS"
METER_FLOOR_DB = -60.0              # level shown as "no signal"
METER_YELLOW_DB = -18.0             # green ... yellow threshold
METER_RED_DB = -6.0                 # yellow ... red threshold
METER_PEAK_DECAY_DB = 6.0           # peak marker fall speed (per update)
METER_WIDTH = 12                    # width of one level meter in pixels

# --- RTA tab (meter bridge) -------------------------------------------------
# The RTA tab re-uses the same "/meters/1" batch as the strip meters and
# shows every meter-capable source of the mixer side by side as one tall
# meter bridge - no extra subscription or network traffic.
RTA_METER_WIDTH = 26                # wider bars than the slim strip meters
RTA_METER_HEIGHT = 340              # taller bars for at-a-glance reading
RTA_SEGMENTS = 20                   # LED segments of one RTA bar

# X AIR scribble-strip colours (OSC int 0 - 15).  The official parameter
# list uses OFF, RD, GN, YE, BL, MG, CY, WH and the same eight again as
# "inverted" variants (black text on a coloured scribble background).
_BASE_SCRIBBLE_COLORS = (
    ("OFF", None),
    ("Red", "#e03131"),
    ("Green", "#2f9e44"),
    ("Yellow", "#f5c211"),
    ("Blue", "#339af0"),
    ("Magenta", "#e64980"),
    ("Cyan", "#15aabf"),
    ("White", "#dee2e6"),
)
SCRIBBLE_COLORS = tuple(
    (index, label, colour)
    for index, (label, colour) in enumerate(_BASE_SCRIBBLE_COLORS)
) + tuple(
    (index + 8, f"{label} (inv)", colour)
    for index, (label, colour) in enumerate(_BASE_SCRIBBLE_COLORS)
)
SCRIBBLE_COLOR_BY_INDEX = {
    index: (label, colour) for index, label, colour in SCRIBBLE_COLORS
}

# --- Colour scheme (dark live-console style) ------------------------------
# Modelled on a modern digital mixer: near-black background, slate cards
# with hairline borders, one electric-blue accent and bright state
# colours.  Every widget reads these constants, so a tweak here restyles
# the whole application.
COL_BG = "#0e1117"          # window background (console black)
COL_BAR = "#12161f"         # top / bottom bar background
COL_STRIP = "#1b2130"       # background of one channel strip (card)
COL_FIELD = "#131826"       # background of the name (scribble) field
COL_CARD_EDGE = "#2a3346"   # hairline border around a strip card
COL_TEXT = "#e8ecf5"        # normal text
COL_TEXT_DIM = "#97a1b5"    # secondary text
COL_BTN_OFF = "#2c3446"     # MUTE/SOLO button, released
COL_BTN_OFF_HL = "#3a4459"  # MUTE/SOLO button, released + hover
COL_RED = "#e5484d"         # MUTE engaged
COL_RED_HL = "#ff6369"      # MUTE engaged + hover
COL_YELLOW = "#f0b429"      # SOLO engaged
COL_YELLOW_HL = "#ffd166"   # SOLO engaged + hover
COL_GREEN = "#2fc26b"       # connected
COL_AMBER = "#ffab2e"       # connecting / warning
COL_RED_STATUS = "#ff6b6b"  # error text
COL_GREY = "#7f8ca6"        # idle text
COL_ACCENT = "#38bdf8"      # highlight colour (MAIN LR, focus, readouts)
COL_ACCENT_DK = "#06283f"   # text drawn on top of the accent colour
COL_LED_OFF = "#333c52"     # status LED, no connection
COL_SEP = "#333d53"         # separator between channels and main
COL_GROOVE = "#0f1420"      # fader groove / meter well


def _hex_rgb(colour: str) -> tuple:
    """'#rrggbb' -> (r, g, b) channel values (0-255)."""
    return (int(colour[1:3], 16), int(colour[3:5], 16),
            int(colour[5:7], 16))


def _rgb_hex(rgb) -> str:
    """(r, g, b) -> '#rrggbb', channels clamped to 0-255."""
    return "#{:02x}{:02x}{:02x}".format(
        *(max(0, min(255, int(round(channel)))) for channel in rgb)
    )


def _mix(colour: str, other: str, t: float) -> str:
    """Blend two colours - 0.0 keeps *colour*, 1.0 returns *other*."""
    a, b = _hex_rgb(colour), _hex_rgb(other)
    return _rgb_hex(a[i] + (b[i] - a[i]) * t for i in range(3))


def _shade(colour: str, amount: float) -> str:
    """Lighten (+) or darken (-) a colour towards white / black."""
    target = "#ffffff" if amount >= 0 else "#000000"
    return _mix(colour, target, abs(amount))


# --- Fonts -----------------------------------------------------------------
FONT = ("Segoe UI", 9)
FONT_SMALL = ("Segoe UI", 8)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_BTN = ("Segoe UI", 8, "bold")
FONT_TITLE = ("Segoe UI", 13, "bold")    # brand line in the top bar
FONT_MONO = ("Consolas", 9)              # numeric readouts
FONT_MONO_BOLD = ("Consolas", 9, "bold") # fader percentage readout

# --- Connection states -----------------------------------------------------
DISCONNECTED = "disconnected"
CONNECTING = "connecting"
CONNECTED = "connected"


# ===========================================================================
# 2. Strip model - OSC address helpers
# ===========================================================================
# Every strip of the mixer is identified by a simple key:
#   integer 1..18  -> input channel CH01..CH18
#   MAIN_STRIP     -> Main LR output

ALL_STRIPS = tuple(range(1, NUM_CHANNELS + 1)) + (MAIN_STRIP,)
BUS_STRIPS = tuple(f"b{n}" for n in range(1, NUM_BUSES + 1))
FX_STRIPS = tuple(f"f{n}" for n in range(1, NUM_FX + 1))
DCA_STRIPS = tuple(f"d{n}" for n in range(1, NUM_DCAS + 1))


def _bus_number(strip):
    """Bus number 1..6 for the AUX strip keys, else None."""
    if isinstance(strip, str) and len(strip) == 2 and strip[0] == "b":
        if strip[1].isdigit():
            number = int(strip[1])
            if 1 <= number <= NUM_BUSES:
                return number
    return None


def _fx_number(strip):
    """FX number 1..4 for the FX strip keys, else None."""
    if isinstance(strip, str) and len(strip) == 2 and strip[0] == "f":
        if strip[1].isdigit():
            number = int(strip[1])
            if 1 <= number <= NUM_FX:
                return number
    return None


def _dca_number(strip):
    """DCA number 1..4 for the DCA strip keys, else None."""
    if isinstance(strip, str) and len(strip) == 2 and strip[0] == "d":
        if strip[1].isdigit():
            number = int(strip[1])
            if 1 <= number <= NUM_DCAS:
                return number
    return None


def strip_label(strip) -> str:
    """Human readable name of a strip, used in messages and labels."""
    if strip == MAIN_STRIP:
        return "Main LR"
    bus = _bus_number(strip)
    if bus is not None:
        return f"AUX{bus}"
    fx = _fx_number(strip)
    if fx is not None:
        return f"FX{fx}"
    dca = _dca_number(strip)
    if dca is not None:
        return f"DCA{dca}"
    return f"CH{int(strip):02d}"


def fader_address(strip) -> str:
    """OSC address of the strip fader (float 0.0 ... 1.0)."""
    if strip == MAIN_STRIP:
        return "/lr/mix/fader"
    bus = _bus_number(strip)
    if bus is not None:
        return f"/bus/{bus}/mix/fader"       # buses use a SINGLE digit
    fx = _fx_number(strip)
    if fx is not None:
        return f"/rtn/{fx}/mix/fader"        # FX returns, also single digit
    dca = _dca_number(strip)
    if dca is not None:
        # NOTE: DCAs have NO "mix" level - the X AIR puts the fader
        # directly under /dca/<n>/fader (verified in Parameters.txt).
        return f"/dca/{dca}/fader"
    return f"/ch/{int(strip):02d}/mix/fader"


def mute_address(strip) -> str:
    """OSC address of the mute switch (0 = muted, 1 = unmuted)."""
    if strip == MAIN_STRIP:
        return "/lr/mix/on"
    bus = _bus_number(strip)
    if bus is not None:
        return f"/bus/{bus}/mix/on"
    fx = _fx_number(strip)
    if fx is not None:
        return f"/rtn/{fx}/mix/on"
    dca = _dca_number(strip)
    if dca is not None:
        # Like the fader: no "mix" level on the X AIR DCA addresses.
        return f"/dca/{dca}/on"
    return f"/ch/{int(strip):02d}/mix/on"


def _solosw_index(strip) -> int:
    """Number of the solo switch that belongs to a strip.

    X AIR solo switch table (index = 0-based source id + 1):
        01..16 -> CH01..CH16, 17 -> AUX input (CH17/CH18 share it),
        18..21 -> FX returns 1..4, 22..39 -> USB, 40..45 -> Bus 1..6,
        46..49 -> FX sends, 50 -> Main LR, 51..54 -> DCA 1..4.
    """
    if strip == MAIN_STRIP:
        return 50
    bus = _bus_number(strip)
    if bus is not None:
        return 39 + bus              # BUS1 -> solosw/40 ... BUS6 -> solosw/45
    fx = _fx_number(strip)
    if fx is not None:
        return 17 + fx               # FX1 -> solosw/18 ... FX4 -> solosw/21
    dca = _dca_number(strip)
    if dca is not None:
        return 50 + dca              # DCA1 -> solosw/51 ... DCA4 -> solosw/54
    return min(int(strip), 17)       # CH17 and CH18 both drive switch 17


def solo_address(strip) -> str:
    """OSC address of the solo switch of a strip (0/1)."""
    return f"/-stat/solosw/{_solosw_index(strip):02d}"


def name_address(strip) -> str:
    """OSC address of the scribble-strip name of a strip (string)."""
    if strip == MAIN_STRIP:
        return "/lr/config/name"
    bus = _bus_number(strip)
    if bus is not None:
        return f"/bus/{bus}/config/name"
    fx = _fx_number(strip)
    if fx is not None:
        return f"/rtn/{fx}/config/name"
    dca = _dca_number(strip)
    if dca is not None:
        return f"/dca/{dca}/config/name"
    return f"/ch/{int(strip):02d}/config/name"


def color_address(strip) -> str:
    """OSC address of the scribble-strip colour of a strip (int 0-15)."""
    if strip == MAIN_STRIP:
        return "/lr/config/color"
    bus = _bus_number(strip)
    if bus is not None:
        return f"/bus/{bus}/config/color"
    fx = _fx_number(strip)
    if fx is not None:
        return f"/rtn/{fx}/config/color"
    dca = _dca_number(strip)
    if dca is not None:
        return f"/dca/{dca}/config/color"
    return f"/ch/{int(strip):02d}/config/color"


def default_name_of(strip) -> str:
    """Local default label shown until the mixer reports a real name."""
    if strip == MAIN_STRIP:
        return "MAIN LR"
    bus = _bus_number(strip)
    if bus is not None:
        return f"AUX{bus}"
    fx = _fx_number(strip)
    if fx is not None:
        return f"FX{fx}"
    dca = _dca_number(strip)
    if dca is not None:
        return f"DCA{dca}"
    return str(int(strip))


# ---------------------------------------------------------------------------
# Channel editor: input source, noise gate, EQ, compressor, sends, main
# ---------------------------------------------------------------------------
# These are the "/ch/NN/..." detail parameters that the channel editor
# window (double-click on a "CH01" ... "CH18" label) reads and writes.
# The X AIR protocol encodes them like this:
#   * "bool"  -> integer 0/1 (1 = ON),
#   * "enum"  -> integer index into a name tuple (ratios, EQ types, ...),
#   * "lin"   -> float 0.0..1.0 mapped linearly onto the real range
#                (gate threshold -80..0 dB),
#   * "log"   -> float 0.0..1.0 mapped logarithmically
#                (hold 0.02..2000 ms, EQ frequency 20..20000 Hz),
#   * "send"  -> float 0.0..1.0 used as-is (channel send level),
#   * "group" -> integer bitmask, one bit per group (bit 0 = group 1 ...
#                bit 3 = group 4) - the DCA and mute group assignments
#                of this channel share ONE address per family.

AUX_SEND_COUNT = 6                   # /ch/NN/mix/01..06/level -> Bus 1-6
FX_SEND_COUNT = 4                    # /ch/NN/mix/07..10/level -> FX 1-4

EQ_TYPES = ("LCut", "LShv", "PEQ", "VEQ", "HShv", "HCut")   # eq/NN/type 0-5
GATE_MODES = ("GATE", "EXP2", "EXP3", "EXP4", "DUCK")       # gate/mode 0-4
DYN_MODES = ("COMP", "EXP")           # dyn/mode   0-1
DYN_DETECTORS = ("PEAK", "RMS")       # dyn/det    0-1
DYN_ENVELOPES = ("LIN", "LOG")        # dyn/env    0-1
DYN_RATIOS = (1.1, 1.3, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0,
              10.0, 20.0, 100.0)      # dyn/ratio  0-11
FILTER_TYPES = ("LC6", "LC12", "HC6", "HC12",
                "1.0", "2.0", "3.0", "5.0", "10.0")         # filter 0-8
KEY_SOURCES = (("SELF",)
               + tuple(f"CH{n:02d}" for n in range(1, 17))
               + tuple(f"BUS{n}" for n in range(1, NUM_BUSES + 1)))
# KEY_SOURCES: 23 entries -> keysrc integer 0..22 (SELF, Ch01..16, Bus1..6)


def _build_channel_detail_specs() -> tuple:
    """(osc suffix, kind, low, high) of every channel editor parameter."""
    specs = [
        ("config/insrc", "enum", None, None),       # input source
        ("gate/on", "bool", None, None),
        ("gate/mode", "enum", None, None),
        ("gate/thr", "lin", -80.0, 0.0),            # dB
        ("gate/range", "lin", 3.0, 60.0),           # dB
        ("gate/attack", "lin", 0.0, 120.0),         # ms
        ("gate/hold", "log", 0.02, 2000.0),         # ms
        ("gate/release", "log", 5.0, 4000.0),       # ms
        ("gate/keysrc", "enum", None, None),
        ("gate/filter/on", "bool", None, None),
        ("gate/filter/type", "enum", None, None),
        ("gate/filter/f", "log", 20.0, 20000.0),    # Hz
        ("eq/on", "bool", None, None),
        ("dyn/on", "bool", None, None),
        ("dyn/mode", "enum", None, None),
        ("dyn/det", "enum", None, None),
        ("dyn/env", "enum", None, None),
        ("dyn/thr", "lin", -60.0, 0.0),             # dB
        ("dyn/ratio", "enum", None, None),
        ("dyn/knee", "lin", 0.0, 5.0),              # dB
        ("dyn/mgain", "lin", 0.0, 24.0),            # dB
        ("dyn/attack", "lin", 0.0, 120.0),          # ms
        ("dyn/hold", "log", 0.02, 2000.0),          # ms
        ("dyn/release", "log", 5.0, 4000.0),        # ms
        ("dyn/mix", "lin", 0.0, 100.0),             # percent
        ("dyn/keysrc", "enum", None, None),
        ("dyn/auto", "bool", None, None),
        ("dyn/filter/on", "bool", None, None),
        ("dyn/filter/type", "enum", None, None),
        ("dyn/filter/f", "log", 20.0, 20000.0),     # Hz
        ("mix/pan", "lin", -100.0, 100.0),
        ("mix/lr", "bool", None, None),             # route channel to Main
        # Group assignments: ONE bitmask address per family (official
        # Parameters.txt: "/ch/NN/grp/dca" and "/ch/NN/grp/mute", int
        # 0-15, "%0000" = 4 bits, bit 0 = group 1 ... bit 3 = group 4).
        ("grp/dca", "group", None, None),           # DCA 1-4 membership
        ("grp/mute", "group", None, None),          # mute group 1-4 membership
    ]
    for band in range(1, 5):                        # EQ bands 1-4
        specs.extend([
            (f"eq/{band}/type", "enum", None, None),
            (f"eq/{band}/f", "log", 20.0, 20000.0),  # Hz
            (f"eq/{band}/g", "lin", -15.0, 15.0),    # dB
            (f"eq/{band}/q", "log", 10.0, 0.3),
        ])
    for n in range(1, AUX_SEND_COUNT + FX_SEND_COUNT + 1):
        specs.append((f"mix/{n:02d}/level", "send", None, None))
    return tuple(specs)


CH_DETAIL_SPECS = _build_channel_detail_specs()
CH_DETAIL_SUFFIXES = frozenset(spec[0] for spec in CH_DETAIL_SPECS)


def channel_param_address(channel: int, suffix: str) -> str:
    """/ch/<nn>/<suffix> with the usual zero padded channel number."""
    return f"/ch/{int(channel):02d}/{suffix}"


def channel_detail_addresses(channel: int) -> tuple:
    """Every editor parameter address of one channel (queried on open)."""
    return tuple(channel_param_address(channel, spec[0])
                 for spec in CH_DETAIL_SPECS)


# The preamp gain is NOT a "/ch/NN/..." parameter - it lives in the
# separate head-amp block at "/headamp/NN/gain" (float 0.0 ... 1.0).
# Firmware maps it linearly onto -12 ... +60 dB for headamps 01..16;
# headamps 17..24 (which no X AIR input exposes) use -12 ... +20, which
# is the range the official Parameters.txt table prints for every
# headamp.  Sources: pmaillot's XAirSetSceneParse.c
# (Xp_linf(-12., 72., ...) for headamps 01-16), xair-api-python
# (lin_get(-12, 60, ...)) and community tests (Bome forum: the mixer
# accepts up to +60 dB).
HEADAMP_GAIN_LO = -12.0                # real dB at protocol value 0.0
HEADAMP_GAIN_HI = 60.0                 # real dB at protocol value 1.0


def gain_address(channel: int) -> str:
    """/headamp/<nn>/gain of an input channel (float 0.0 ... 1.0)."""
    return f"/headamp/{int(channel):02d}/gain"


def channel_editor_addresses(channel: int) -> tuple:
    """Every address the editor window reads when it opens.

    The 60 detail parameters (including the two group bitmasks),
    the preamp gain and the two addresses the window shares with
    the strip (Main level fader + MUTE switch).
    """
    return (channel_detail_addresses(channel)
            + (gain_address(channel), fader_address(channel),
               mute_address(channel)))


def source_choices(count: int) -> tuple:
    """Entry list of "/ch/NN/config/insrc" for a model with *count* inputs.

    The X AIR numbers its sources IN 01 ... IN <count>, then offers the
    AUX left/right pair and finally OFF - 19 entries on an XR16
    (official range 0..18), 21 on an XR18 (range 0..20).
    """
    choices = [f"IN {n:02d}" for n in range(1, count + 1)]
    choices += ["L (AUX)", "R (AUX)", "OFF"]
    return tuple(choices)


def norm_to_real(kind: str, lo: float, hi: float, norm: float) -> float:
    """Denormalise a 0..1 protocol value onto its real range."""
    norm = _clamp01(float(norm))
    if kind == "log":
        return lo * (hi / lo) ** norm
    return lo + norm * (hi - lo)


def real_to_norm(kind: str, lo: float, hi: float, real: float) -> float:
    """Normalise a real parameter value into the 0..1 protocol value."""
    if kind == "log":
        real = max(lo, min(hi, float(real)))
        return math.log(real / lo) / math.log(hi / lo)
    if hi == lo:
        return 0.0
    return _clamp01((float(real) - lo) / (hi - lo))


# -- readouts shown next to the editor sliders -----------------------------

def fmt_db(value: float) -> str:
    return f"{value:.1f} dB"


def fmt_db0(value: float) -> str:
    return f"{value:.0f} dB"


def fmt_db_signed(value: float) -> str:
    return f"{value:+.1f} dB"


def fmt_ms(value: float) -> str:
    if value < 1.0:
        return f"{value:.2f} ms"
    if value < 100.0:
        return f"{value:.1f} ms"
    return f"{value:.0f} ms"


def fmt_hz(value: float) -> str:
    if value >= 1000.0:
        return f"{value / 1000.0:.2f} kHz"
    return f"{value:.0f} Hz"


def fmt_plain(value: float) -> str:
    return f"{value:.1f}"


def fmt_q(value: float) -> str:
    return f"{value:.2f}"


def fmt_percent(value: float) -> str:
    return f"{value:.0f}%"


def fmt_pan(value: float) -> str:
    if abs(value) < 1.0:
        return "Center"
    return f"{value:+.0f}"


# ---------------------------------------------------------------------------
# Configuration file (last mixer IP address)
# ---------------------------------------------------------------------------
# A tiny JSON dictionary is stored next to this script so the mixer
# address survives an application restart.  Everything is best-effort:
# a missing, unreadable or broken file simply behaves like an empty one.

def load_config() -> dict:
    """Read the configuration file; any problem -> empty config."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def update_config(**values) -> bool:
    """Merge the given key/values into the config file.

    Returns True when the file was written, False when it could not be
    created (read-only folder, ...).  Existing other keys are kept.
    """
    data = load_config()
    data.update(values)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Error log file
# ---------------------------------------------------------------------------
# Everything that goes wrong is appended to a small rotating text file
# next to this script (xr_remote.log), so a problem can still be read
# after the short-lived status bar message has vanished - and when the
# application is started by double-clicking it, stderr is not visible
# either, which makes the file the only record of a crash.
#
# What ends up in the file:
#   * every red status bar message (network/OSC failures, timeouts,
#     connection lost, errors reported by the OSC threads),
#   * unhandled exceptions with their full traceback (sys.excepthook),
#   * crashes inside Tk callbacks with their full traceback
#     (root.report_callback_exception),
#   * explicit log_error()/log_warning() calls.
#
# Everything here is BEST EFFORT: when the folder is read-only or the
# file cannot be written, file logging silently stays off (one failed
# attempt only) - the application must never break because of its own
# log book.  The stdlib "logging" module is used because it is
# thread-safe (the OSC thread logs too) and provides the file rotation.

_LOG_FORMAT = "%(asctime)s  %(levelname)-7s %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
_log = logging.getLogger("xr_remote")   # handler is attached by setup_logging()
# The log goes to the FILE ONLY: python-osc's dispatcher can trigger a
# lazy logging.basicConfig() on the root logger (its "No handler matched
# ..." debug line), which would otherwise echo every record to stderr.
_log.propagate = False
_log_handler = None       # active RotatingFileHandler (None = logging off)
_log_handler_path = None  # file that handler writes to
_log_setup_tried = False  # one automatic open attempt only


def setup_logging(path=None):
    """Open (or re-open) the rotating log file; return its path or None.

    main() calls this once at start-up.  Tests (or a changed LOG_FILE)
    may pass their own *path*; calling it again with a different path
    swaps the handler atomically - if the NEW file cannot be opened the
    old handler keeps running and None is returned.  Any failure simply
    disables file logging (best effort, never raises).
    """
    global _log_handler, _log_handler_path, _log_setup_tried
    target = Path(path) if path is not None else LOG_FILE
    if _log_handler is not None and _log_handler_path == target:
        return target                   # already writing to that file
    try:
        handler = logging.handlers.RotatingFileHandler(
            target, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
            encoding="utf-8",
        )
    except OSError:
        # Missing directory / read-only folder: remember the attempt so
        # the automatic first-use path does not hammer the disk, and
        # keep any previous handler running.
        _log_setup_tried = True
        return None
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATEFMT))
    _log.setLevel(logging.INFO)
    if _log_handler is not None:        # swapping to a new path
        _log.removeHandler(_log_handler)
        _log_handler.close()
    _log.addHandler(handler)
    _log_handler = handler
    _log_handler_path = target
    _log_setup_tried = True
    return target


def _log_write(level: int, message: str) -> None:
    """Write one line to the log file; never raises.

    The first use tries to open LOG_FILE automatically so the simple
    log_error("...") calls need no setup in the normal application.
    """
    if _log_handler is None:
        if _log_setup_tried:
            return                      # known to be unavailable - stay off
        if setup_logging() is None:
            return                      # could not open - stay silent
    _log.log(level, str(message))


def log_error(message: str) -> None:
    """Append an ERROR line to the log file (never raises)."""
    _log_write(logging.ERROR, message)


def log_warning(message: str) -> None:
    """Append a WARNING line to the log file (never raises)."""
    _log_write(logging.WARNING, message)


def _format_exception(exc_type, exc_value, exc_tb) -> str:
    """Full traceback of an exception as printable text."""
    return "".join(traceback.format_exception(exc_type, exc_value,
                                              exc_tb)).rstrip()


def _install_excepthook() -> None:
    """Send uncaught exceptions to the log file (call once, from main).

    The previous hook (which prints to stderr) still runs afterwards,
    so nothing is swallowed when a console is attached.
    """
    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        log_error("Unhandled exception:\n"
                  + _format_exception(exc_type, exc_value, exc_tb))
        previous(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def _report_callback_exception(exc_type, exc_value, exc_tb) -> None:
    """Crash inside a Tk callback -> log the traceback (and print it).

    Installed on the root window as root.report_callback_exception;
    without it Tkinter would only print to stderr, which a windowed
    start does not show at all.
    """
    text = _format_exception(exc_type, exc_value, exc_tb)
    log_error("Unhandled Tk callback exception:\n" + text)
    print(text, file=sys.stderr)


# ---------------------------------------------------------------------------
# Mixer model -> number of channel faders
# ---------------------------------------------------------------------------

def channel_count_from_model(model: str):
    """Number of input channels of an X AIR model, or None if unknown.

    The "/xinfo" reply names the mixers "X12", "X16" and "X18" (the
    tabletop XR-series names like "XR18" contain the same digits), so
    the channel count is simply read out of that model string.  Unknown
    models (e.g. an X32, which speaks a different protocol) return None
    and the fader bank keeps its current size.
    """
    text = str(model or "").upper()
    for count in (18, 16, 12):          # longest number first (18 vs 1...)
        if str(count) in text:
            return count
    return None


# Reverse lookup: solo switch number -> strips that it controls.
# CH17/CH18 share one switch, therefore a switch can map to two strips.
_SOLOSW_TO_STRIPS: dict[str, tuple] = {}
for _strip in ALL_STRIPS + BUS_STRIPS + FX_STRIPS + DCA_STRIPS:
    _key = f"{_solosw_index(_strip):02d}"
    _SOLOSW_TO_STRIPS.setdefault(_key, []).append(_strip)
_SOLOSW_TO_STRIPS = {k: tuple(v) for k, v in _SOLOSW_TO_STRIPS.items()}


# ---------------------------------------------------------------------------
# Level meter index table (meter id 1 - "ALL CHANNELS" blob, 40 values)
# ---------------------------------------------------------------------------
#   0..15  CH01..CH16 pre-fader      16..17  AUX in L/R (= CH17/CH18)
#   18..25 FX1..FX4 pre-fader L/R    26..31  Bus 1..6 pre-fader
#   32..35 FX send 1..4              36..37  Main L/R post-fader
#   38..39 Monitor L/R (not shown in this application)

def _build_meter_indices() -> dict:
    """Map every strip of this application to its blob index/indices.

    Stereo sources (FX returns, Main LR) list both channels; the GUI
    shows the louder of the two.
    """
    table = {}
    for number in range(1, NUM_CHANNELS + 1):
        table[number] = (number - 1,)        # CH01..CH18 -> 0..17
    for fx in range(1, NUM_FX + 1):
        table[f"f{fx}"] = (16 + 2 * fx, 17 + 2 * fx)   # FX1 -> 18,19 ...
    for bus in range(1, NUM_BUSES + 1):
        table[f"b{bus}"] = (25 + bus,)       # Bus1 -> 26 ... Bus6 -> 31
    table[MAIN_STRIP] = (36, 37)             # Main L/R
    return table


METER_INDICES = _build_meter_indices()


def parse_meter_blob(data) -> list:
    """Decode a meter blob into a list of dB values.

    Format (per the official X AIR OSC document): an int32 count in
    little endian, followed by that many signed int16 values with a
    resolution of 1/256 dB.  Malformed blobs -> [].
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 4:
        return []
    try:
        (count,) = struct.unpack_from("<i", data, 0)
        count = max(0, min(count, (len(data) - 4) // 2))
        raw = struct.unpack_from(f"<{count}h", data, 4)
    except struct.error:
        return []
    return [value / 256.0 for value in raw]


def parse_parameter(address: str):
    """Translate an incoming OSC address into [(kind, strip), ...].

    Returns an empty list for addresses this application does not care
    about (meters, EQ, bus sends, acknowledgement of "/xremote", ...).
    """
    # --- Main LR ---------------------------------------------------------
    if address == "/lr/mix/fader":
        return [("fader", MAIN_STRIP)]
    if address == "/lr/mix/on":
        return [("mute", MAIN_STRIP)]
    if address == "/lr/config/name":
        return [("name", MAIN_STRIP)]
    if address == "/lr/config/color":
        return [("color", MAIN_STRIP)]

    # --- solo switches ---------------------------------------------------
    if address.startswith("/-stat/solosw/"):
        index = address.rsplit("/", 1)[-1]
        strips = _SOLOSW_TO_STRIPS.get(index)
        return [("solo", strip) for strip in strips] if strips else []

    # --- channels: /ch/<nn>/mix/fader, /ch/<nn>/mix/on, /ch/<nn>/config/name
    parts = address.split("/")
    if len(parts) == 5 and parts[1] == "ch" and parts[2].isdigit():
        number = int(parts[2])
        if not 1 <= number <= NUM_CHANNELS:
            return []
        if parts[3] == "mix" and parts[4] == "fader":
            return [("fader", number)]
        if parts[3] == "mix" and parts[4] == "on":
            return [("mute", number)]
        if parts[3] == "config" and parts[4] == "name":
            return [("name", number)]
        if parts[3] == "config" and parts[4] == "color":
            return [("color", number)]

    # --- channel detail parameters (input source, gate, EQ, dyn, sends) ---
    # Anything else under /ch/<nn>/... that the channel editor window
    # knows about: reported as ("chparam", (channel, canonical address))
    # so the open editor can update the matching widget.
    if len(parts) >= 4 and parts[1] == "ch" and parts[2].isdigit():
        number = int(parts[2])
        if 1 <= number <= NUM_CHANNELS:
            suffix = "/".join(parts[3:])
            if suffix in CH_DETAIL_SUFFIXES:
                return [("chparam", (number, channel_param_address(
                    number, suffix)))]

    # --- preamp gain: /headamp/<nn>/gain (channel number, zero padded) ---
    # Lives outside /ch (see gain_address); same chparam event as the
    # other channel editor values so the open window can update it.
    if (len(parts) == 4 and parts[1] == "headamp" and parts[2].isdigit()
            and parts[3] == "gain"):
        number = int(parts[2])
        if 1 <= number <= NUM_CHANNELS:
            return [("chparam", (number, gain_address(number)))]

    # --- AUX buses: /bus/<n>/mix/fader, /bus/<n>/mix/on, /bus/<n>/config/...
    # The X AIR uses a SINGLE digit for buses ("/bus/1/...", not
    # "/bus/01/..."); int() accepts both spellings here.
    if len(parts) == 5 and parts[1] == "bus" and parts[2].isdigit():
        number = int(parts[2])
        if not 1 <= number <= NUM_BUSES:
            return []
        strip = f"b{number}"
        if parts[3] == "mix" and parts[4] == "fader":
            return [("fader", strip)]
        if parts[3] == "mix" and parts[4] == "on":
            return [("mute", strip)]
        if parts[3] == "config" and parts[4] == "name":
            return [("name", strip)]
        if parts[3] == "config" and parts[4] == "color":
            return [("color", strip)]

    # --- FX returns: /rtn/<n>/mix/fader, /rtn/<n>/mix/on, /rtn/<n>/config/...
    # Same single-digit convention as the buses.  "/rtn/aux/..." (the
    # USB/aux return) is not a strip of this application and is ignored.
    if len(parts) == 5 and parts[1] == "rtn" and parts[2].isdigit():
        number = int(parts[2])
        if not 1 <= number <= NUM_FX:
            return []
        strip = f"f{number}"
        if parts[3] == "mix" and parts[4] == "fader":
            return [("fader", strip)]
        if parts[3] == "mix" and parts[4] == "on":
            return [("mute", strip)]
        if parts[3] == "config" and parts[4] == "name":
            return [("name", strip)]
        if parts[3] == "config" and parts[4] == "color":
            return [("color", strip)]

    # --- DCAs: /dca/<n>/fader, /dca/<n>/on, /dca/<n>/config/name|color
    # NOTE: unlike channels/buses/FX returns, the X AIR DCA fader and
    # mute have NO "mix" level ("/dca/1/fader", not "/dca/1/mix/fader";
    # verified in the official Parameters.txt).  Single digit like the
    # buses.  DCAs have no channel editor page and no level meter (the
    # ALL CHANNELS blob does not include them).
    if len(parts) >= 4 and parts[1] == "dca" and parts[2].isdigit():
        number = int(parts[2])
        if not 1 <= number <= NUM_DCAS:
            return []
        strip = f"d{number}"
        if len(parts) == 4 and parts[3] == "fader":
            return [("fader", strip)]
        if len(parts) == 4 and parts[3] == "on":
            return [("mute", strip)]
        if len(parts) == 5 and parts[3] == "config" and parts[4] == "name":
            return [("name", strip)]
        if len(parts) == 5 and parts[3] == "config" and parts[4] == "color":
            return [("color", strip)]

    return []


def _to_bool(value) -> bool:
    """Tolerant conversion of an OSC argument to a boolean.

    The mixer normally sends integers, but some firmware builds echo
    booleans (OSC 'T'/'F' tags) or floats - all of them are handled.
    """
    if isinstance(value, bool):
        return value
    return int(round(float(value))) != 0


def _clamp01(value: float) -> float:
    """Clamp a fader value into the valid 0.0 ... 1.0 range."""
    return max(0.0, min(1.0, float(value)))


# ===========================================================================
# 3. OSC communication layer  (no GUI code in here!)
# ===========================================================================

class OscMixer:
    """All UDP/OSC logic of the application.

    The object owns exactly one UDP socket - the one created by
    BlockingOSCUDPServer.  Sending through *that* socket guarantees that
    the mixer's replies (which go back to our source port) are received
    by our own dispatcher.

    Thread model:
      * start() launches a daemon thread that runs the receive loop.
      * send() may be called from any thread (GUI thread in practice).
      * Everything received from the mixer is forwarded to the GUI as a
        simple tuple through the thread-safe "events" queue.  The GUI
        never touches a socket and the OSC thread never touches a widget.
    """

    def __init__(self, events: "queue.Queue"):
        self.events = events            # mailbox GUI <- OSC thread
        self._target_ip: str | None = None
        self._server: BlockingOSCUDPServer | None = None
        self._rx_thread: threading.Thread | None = None
        self._send_lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Create the UDP socket and start the background receive loop."""
        if self._server is not None:
            return

        dispatcher = Dispatcher()
        # One single catch-all handler keeps the routing logic simple and
        # robust: parse_parameter() decides what to do with each address.
        dispatcher.set_default_handler(self._handle_message)

        # Bind to every local interface; port 0 lets the OS pick a free
        # source port - the mixer does not care which one we use, it just
        # answers to whatever port our request came from.
        try:
            self._server = BlockingOSCUDPServer(("0.0.0.0", 0), dispatcher)
        except OSError as exc:
            raise RuntimeError(
                f"Could not open a UDP receive socket on this machine:\n{exc}"
            ) from exc

        self._rx_thread = threading.Thread(
            target=self._serve, name="xr-osc-rx", daemon=True
        )
        self._rx_thread.start()

    def _serve(self) -> None:
        """Receive loop - runs inside its own daemon thread."""
        try:
            # poll_interval keeps the loop responsive for shutdown().
            self._server.serve_forever(poll_interval=0.2)
        except Exception as exc:                     # pragma: no cover
            self.events.put(("error", f"OSC receive loop stopped: {exc}"))

    def stop(self) -> None:
        """Stop the receive loop and close the socket (app shutdown)."""
        server = self._server
        if server is None:
            return
        self._server = None
        self._target_ip = None
        try:
            server.shutdown()          # waits until serve_forever() exits
        finally:
            try:
                server.server_close()
            except OSError:
                pass
            if self._rx_thread is not None:
                self._rx_thread.join(timeout=2.0)
            self._rx_thread = None

    # -- connection management --------------------------------------------

    @property
    def has_target(self) -> bool:
        """True when a mixer IP address is currently selected."""
        return self._target_ip is not None

    @property
    def local_port(self) -> int:
        """The local UDP port this client listens on (0 = not started)."""
        server = self._server
        if server is None:
            return 0
        return server.socket.getsockname()[1]

    def connect(self, ip: str) -> None:
        """Select the mixer and ping it with "/xinfo".

        The console state itself is loaded by the GUI (see
        MixerGUI._request_console_state) once the ping answer has
        confirmed that the mixer is really alive - that way the state
        query never floods an unreachable network.

        Raises ValueError for an unusable address and RuntimeError when
        the receive socket was not started.
        """
        if self._server is None:
            raise RuntimeError("The OSC client has not been started.")
        # ipaddress validates and normalises (e.g. strips whitespace).
        self._target_ip = str(ipaddress.IPv4Address(ip.strip()))
        # Ping / identification - the answer proves the mixer is alive.
        self.send("/xinfo")

    def disconnect(self) -> None:
        """Forget the mixer address (late replies are simply ignored)."""
        self._target_ip = None

    def query_strips(self, strips) -> None:
        """Request the current fader/mute/solo/name of the given strips.

        A message without argument is the X AIR "parameter enquiry": the
        mixer answers by echoing the current value back to this client.
        """
        for strip in strips:
            self.send(fader_address(strip))
            self.send(mute_address(strip))
            self.send(solo_address(strip))
            self.send(name_address(strip))
            self.send(color_address(strip))

    def query_parameters(self, strips=None) -> None:
        """Request the current value of the given strips' parameters.

        Without an argument the whole default strip set is queried; the
        GUI passes the strips the connected model really has (an XR16
        only gets CH01..CH16 + Main LR).
        """
        self.query_strips(ALL_STRIPS if strips is None else strips)

    def renew_remote(self) -> None:
        """Re-send "/xremote" so the mixer keeps pushing live updates."""
        self.send("/xremote")

    def subscribe_meters(self) -> None:
        """Subscribe to the "ALL CHANNELS" level meter batch.

        The mixer answers with 40 x int16 (1/256 dB) at "/meters/1"
        about every 50 ms - one subscription covers every strip this
        application shows (channels, Main LR, AUX buses, FX returns).
        """
        self.send("/meters", METER_SUBSCRIPTION, METER_ID_ALL_CHANNELS)

    def renew_meters(self) -> None:
        """Keep the meter subscription alive (it stops after ~10 s).

        The mixer ends meter streams that are not renewed, exactly
        like "/xremote" parameter feedback.
        """
        self.send("/renew", METER_SUBSCRIPTION)

    # -- sending ----------------------------------------------------------

    def send(self, address: str, *values) -> bool:
        """Send one OSC message to the mixer.

        Called without values the message carries no argument, which is
        how the X AIR protocol requests a parameter ("query") or is used
        for commands such as /xinfo and /xremote.  With values they are
        attached in the given order (a meter subscription takes two:
        reply address and meter id).

        Returns True when the packet left the socket, False otherwise.
        Network problems are reported to the GUI through the event queue.
        """
        server = self._server
        target = self._target_ip
        if server is None or target is None:
            return False                     # not connected - nothing to do

        builder = OscMessageBuilder(address=address)
        for value in values:
            builder.add_arg(value)
        packet = builder.build().dgram

        try:
            # Sending and receiving share one socket on purpose:
            # the mixer replies to the source port of our request.
            with self._send_lock:
                server.socket.sendto(packet, (target, MIXER_OSC_PORT))
            return True
        except OSError as exc:
            # e.g. "Network is unreachable", "No route to host", cable out
            self.events.put(
                ("error", f"Network error while sending to {target}: {exc}")
            )
            return False

    # Convenience wrappers used by the GUI -------------------------------

    def set_fader(self, strip, value: float) -> bool:
        """Move a fader (value is a normalised 0.0 ... 1.0 float)."""
        return self.send(fader_address(strip), float(_clamp01(value)))

    def set_mute(self, strip, muted: bool) -> bool:
        """Engage (True) or release (False) the mute switch.

        X AIR polarity: /mix/on 0 = muted, /mix/on 1 = unmuted.
        """
        return self.send(mute_address(strip), 0 if muted else 1)

    def set_solo(self, strip, soloed: bool) -> bool:
        """Engage (True) or release (False) the solo switch."""
        return self.send(solo_address(strip), 1 if soloed else 0)

    def set_name(self, strip, name: str) -> bool:
        """Write the scribble-strip name of a strip to the mixer."""
        return self.send(name_address(strip), str(name)[:MAX_NAME_LEN])

    def set_color(self, strip, index: int) -> bool:
        """Write the scribble-strip colour of a strip to the mixer.

        index: 0 = OFF, 1-7 = RD/GN/YE/BL/MG/CY/WH, 8-15 = inverted
        variants of the same colours (black text on coloured background).
        """
        return self.send(color_address(strip),
                         max(0, min(15, int(index))))

    # -- receiving --------------------------------------------------------

    def _handle_message(self, address, *args) -> None:
        """Dispatcher callback - runs in the OSC receive thread.

        It only validates the data and converts it into GUI events; the
        actual widget updates happen later in the Tk main thread.
        """
        try:
            if address == "/xinfo":
                # Reply: (ip, name, model, firmware) as OSC strings.
                self.events.put(("xinfo", tuple(str(a) for a in args)))
                return

            if address == METER_SUBSCRIPTION:
                # Level meter batch: 40 x int16 (1/256 dB) in one blob.
                # A single event carries the whole batch; the GUI
                # distributes it to the individual strip meters.
                values = parse_meter_blob(args[0]) if args else []
                if values:
                    self.events.put(("meters", values))
                return

            if not args:
                return                       # nothing useful to report

            parsed = parse_parameter(address)
            if not parsed:
                return                       # unknown address - ignore

            raw = args[0]
            for kind, strip in parsed:
                if kind == "fader":
                    self.events.put(("fader", strip, _clamp01(raw)))
                elif kind == "mute":
                    # /mix/on: 0 = muted -> GUI event carries "muted".
                    self.events.put(("mute", strip, not _to_bool(raw)))
                elif kind == "solo":
                    # solosw: 1 = solo engaged -> GUI event carries "soloed".
                    self.events.put(("solo", strip, _to_bool(raw)))
                elif kind == "name":
                    # config/name: scribble-strip label (string).
                    self.events.put(("name", strip, str(raw)))
                elif kind == "color":
                    # config/color: scribble colour index 0-15.
                    index = max(0, min(15, int(round(float(raw)))))
                    self.events.put(("color", strip, index))
                elif kind == "chparam":
                    # Detail parameter (gate/EQ/dyn/sends/...) - "strip"
                    # carries (channel, address) for the editor window.
                    self.events.put(("chparam", strip, raw))
        except Exception as exc:              # never kill the RX thread
            self.events.put(
                ("error", f"Invalid OSC message '{address}': {exc}")
            )


# ===========================================================================
# 4. GUI widgets
# ===========================================================================

class FaderWidget(tk.Canvas):
    """A custom drawn vertical audio fader.

    Value mapping: 0.0 = bottom (silence) ... 1.0 = top (loudest).
    The widget is drawn on a Canvas instead of using ttk.Scale so that
    the visual behaviour of a real console fader is guaranteed on every
    platform (and so the orientation can never be inverted by a theme).

    A "dragging" flag protects the user: while the mouse button is held
    down, feedback coming from the mixer cannot move the cap away.
    """

    def __init__(self, master, on_change, **kwargs):
        super().__init__(
            master,
            width=FADER_WIDTH,
            height=FADER_HEIGHT,
            bg=COL_STRIP,
            highlightthickness=0,
            bd=0,
            cursor="sb_v_double_arrow",
            **kwargs,
        )
        self._on_change = on_change          # callback(value: float)
        self._value = 0.75
        self._last_sent = self._value        # throttles OSC traffic
        self._dragging = False
        self._accent = COL_ACCENT            # colour of the groove fill
        self._muted = False                  # muted -> fill turns red

        # Mouse interaction -------------------------------------------------
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)   # Windows / macOS
        self.bind("<Button-4>", self._wheel)     # X11 wheel up
        self.bind("<Button-5>", self._wheel)     # X11 wheel down
        # Redraw when the strip column gives us a different width
        # (for example the wider "MAIN LR" column).
        self.bind("<Configure>", lambda _e: self._redraw())

        self._redraw()

    # -- public API -------------------------------------------------------

    def value(self) -> float:
        """Current fader position (0.0 ... 1.0)."""
        return self._value

    def set_value(self, value: float) -> None:
        """Update from mixer feedback (ignored while the user drags)."""
        if self._dragging:
            return
        value = _clamp01(value)
        if abs(value - self._value) < 1e-9:
            return
        self._value = value
        self._last_sent = value
        self._redraw()

    def set_accent(self, colour: str) -> None:
        """Tint of the groove fill - the strip's scribble colour."""
        if not colour or colour == self._accent:
            return
        self._accent = colour
        self._redraw()

    def set_muted(self, muted: bool) -> None:
        """Muted channels show a red groove fill instead of the accent."""
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self._redraw()

    # -- geometry helpers -------------------------------------------------

    def _travel(self):
        """Y coordinates of the cap centre for value 1.0 and 0.0."""
        cap_half = 8                              # half of the cap height
        top = 12 + cap_half
        bottom = FADER_HEIGHT - 12 - cap_half
        return top, bottom

    def _y_from_value(self, value: float) -> float:
        top, bottom = self._travel()
        return bottom - value * (bottom - top)

    def _value_from_y(self, y: float) -> float:
        top, bottom = self._travel()
        if bottom == top:
            return 0.0
        return _clamp01((bottom - y) / (bottom - top))

    # -- drawing ----------------------------------------------------------

    def _center_x(self) -> float:
        """Horizontal centre of the widget (it may be stretched)."""
        width = self.winfo_width()
        return width / 2.0 if width > 1 else FADER_WIDTH / 2.0

    def _redraw(self) -> None:
        self.delete("all")
        cx = self._center_x()
        y = self._y_from_value(self._value)

        # Recessed groove: dark shadow plate with the inner slot on top
        # in which the cap travels.
        self.create_rectangle(cx - 12, 5, cx + 12, FADER_HEIGHT - 5,
                              fill="#070a10", outline="")
        self.create_rectangle(cx - 8, 7, cx + 8, FADER_HEIGHT - 7,
                              fill=COL_GROOVE, outline="")

        # "Setpoint" fill inside the slot: bottom -> cap position, graded
        # from a dim tint to the full accent so the level is readable
        # from a distance.  Muted channels fill in red instead.
        fill_colour = COL_RED if self._muted else self._accent
        base = _mix(fill_colour, COL_GROOVE, 0.80)
        y_low = FADER_HEIGHT - 8
        if y_low - y >= 2:
            steps = 14
            band = (y_low - y) / steps
            for i in range(steps):
                colour = _mix(base, fill_colour, i / (steps - 1))
                self.create_rectangle(
                    cx - 7, y_low - band * (i + 1), cx + 7,
                    y_low - band * i + 1, fill=colour, outline="",
                )

        # Scale ticks at 0 / 25 / 50 / 75 / 100 %
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            y_t = self._y_from_value(frac)
            self.create_line(cx - 26, y_t, cx - 14, y_t, fill="#46516a")
            self.create_line(cx + 14, y_t, cx + 26, y_t, fill="#46516a")

        # The fader cap: soft drop shadow, silver body with a vertical
        # gradient, outline and three grip lines in the middle.
        x0, x1 = cx - 20, cx + 20
        y0, y1 = y - 9, y + 9
        self.create_rectangle(x0 + 1, y0 + 3, x1 + 1, y1 + 4,
                              fill="#05070c", outline="")
        bands = 5
        for i in range(bands):
            band_top = y0 + (y1 - y0) * i / bands
            band_bottom = y0 + (y1 - y0) * (i + 1) / bands
            self.create_rectangle(
                x0, band_top, x1, band_bottom + 1,
                fill=_mix("#eef2f8", "#97a2b3", i / (bands - 1)),
                outline="",
            )
        self.create_rectangle(x0, y0, x1, y1, outline="#5b6478")
        for offset in (-3, 0, 3):
            self.create_line(x0 + 6, y + offset, x1 - 6, y + offset,
                             fill="#4a5468")

    # -- interaction ------------------------------------------------------

    def _apply(self, y: float, notify: bool) -> None:
        new_value = self._value_from_y(y)
        if abs(new_value - self._value) < 1e-9:
            return                              # no movement
        self._value = new_value
        self._redraw()
        # Throttle: do not flood the network with sub-0.3% steps while the
        # finger is moving; the final position is always sent on release.
        if notify and abs(new_value - self._last_sent) >= 0.003:
            self._last_sent = new_value
            self._on_change(new_value)

    def _press(self, event) -> None:
        self._dragging = True
        self._apply(event.y, notify=True)

    def _drag(self, event) -> None:
        if self._dragging:
            self._apply(event.y, notify=True)

    def _release(self, event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._apply(event.y, notify=True)
        # Make sure the exact release position reaches the mixer.
        if abs(self._value - self._last_sent) > 1e-9:
            self._last_sent = self._value
            self._on_change(self._value)

    def _wheel(self, event) -> None:
        delta = getattr(event, "delta", 0)
        if delta:
            step = 1 if delta > 0 else -1
        elif getattr(event, "num", 0) == 4:
            step = 1
        else:
            step = -1
        new_value = _clamp01(self._value + step * 0.02)
        if abs(new_value - self._value) < 1e-9:
            return
        self._value = new_value
        self._last_sent = new_value
        self._redraw()
        self._on_change(new_value)


class MeterWidget(tk.Canvas):
    """Vertical audio level meter drawn next to a fader.

    Shows the real-time signal level of the strip as 16 LED segments
    (green / yellow / red like the console's meter scale, unlit segments
    stay visible as dark glass) plus a slowly falling peak-hold marker.
    Levels arrive as dB values from the mixer's "/meters/1" batch;
    METER_FLOOR_DB and below renders as "no signal".
    """

    def __init__(self, master, height=FADER_HEIGHT, width=METER_WIDTH,
                 segments=16, **kwargs):
        super().__init__(
            master, width=width, height=height,
            bg="#0a0d13", highlightthickness=0, bd=0, **kwargs,
        )
        self._height = height
        self._segments = segments
        self._level_db = METER_FLOOR_DB
        self._peak_db = METER_FLOOR_DB
        self.bind("<Configure>", lambda _e: self._redraw())
        self._redraw()

    # -- values ------------------------------------------------------------

    @property
    def level_db(self) -> float:
        """Currently displayed level in dB (METER_FLOOR_DB = silence)."""
        return self._level_db

    @property
    def peak_db(self) -> float:
        """Peak-hold marker in dB."""
        return self._peak_db

    def set_db(self, db: float) -> None:
        """Feed one meter value (dB) into the widget."""
        self._level_db = max(METER_FLOOR_DB, min(0.0, float(db)))
        if self._level_db >= self._peak_db:
            self._peak_db = self._level_db
        else:
            # fall a little with every update - reads like a real meter
            self._peak_db = max(self._level_db,
                                self._peak_db - METER_PEAK_DECAY_DB)
        self._redraw()

    def clear(self) -> None:
        """Drop back to silence (connection closed)."""
        self._level_db = METER_FLOOR_DB
        self._peak_db = METER_FLOOR_DB
        self._redraw()

    # -- drawing -----------------------------------------------------------

    def _norm(self, db: float) -> float:
        """Map dB to 0.0 (floor) ... 1.0 (0 dBFS)."""
        if db <= METER_FLOOR_DB:
            return 0.0
        return (db - METER_FLOOR_DB) / (0.0 - METER_FLOOR_DB)

    def _y(self, db: float) -> int:
        """Pixel row of a dB value (0 = top of the meter)."""
        return int(round(self._height - self._norm(db) * self._height))

    def _redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        if width <= 4:
            width = METER_WIDTH            # not mapped yet
        height = self._height
        segments = self._segments             # LED segments of the meter
        self.create_rectangle(0, 0, width - 1, height - 1,
                              fill="#0a0d13", outline="")

        # Lit segments from the bottom up; each segment gets its colour
        # from the dB range its centre sits in (green / yellow / red).
        step = height / segments
        level_norm = self._norm(self._level_db)
        lit = 0
        if level_norm > 0.0:
            lit = int(level_norm * segments + 0.9999)   # ceil, 1 ... 16
        for i in range(segments):
            centre_db = (METER_FLOOR_DB
                         + ((i + 0.5) / segments) * (0.0 - METER_FLOOR_DB))
            if centre_db > METER_RED_DB:
                colour = COL_RED
            elif centre_db > METER_YELLOW_DB:
                colour = COL_YELLOW
            else:
                colour = COL_GREEN
            # segment i counts from the bottom, 1 px gap between segments
            top_edge = height - (i + 1) * step
            bottom_edge = height - i * step
            y0 = 0 if i == segments - 1 else int(round(top_edge)) + 1
            y1 = int(round(bottom_edge)) - 1
            if y1 < y0:
                continue
            if i < lit:
                fill = colour
            else:
                # unlit: the same colour dimmed almost to black, like a
                # switched-off LED behind smoked glass
                fill = _mix(colour, "#0a0d13", 0.85)
            self.create_rectangle(1, y0, width - 2, y1, fill=fill, outline="")

        # peak-hold marker
        if self._peak_db > METER_FLOOR_DB:
            peak_y = self._y(self._peak_db)
            self.create_line(1, peak_y, width - 2, peak_y,
                             fill="#f8fafc", width=2)


class StripColumn(tk.Frame):
    """    One complete channel strip:

        +-----------+
        |   CH01    |   name label
        |  [fader]| |  vertical fader + level meter
        |    67%    |   value readout
        |   MUTE    |   changes colour when engaged (red)
        |   SOLO    |   changes colour when engaged (yellow)
        |    1      |   scribble name field - double-click to rename,
        +-----------+   right-click to choose the name colour
    """

    def __init__(self, master, strip, *, label_text, is_main=False,
                 name_default=None, has_meter=True,
                 on_fader, on_mute, on_solo, on_name,
                 on_color, on_wheel=None, on_header=None):
        super().__init__(master, bg=COL_STRIP, padx=5, pady=6,
                         highlightthickness=1,
                         highlightbackground=COL_CARD_EDGE)
        self.strip = strip
        self._is_main = is_main
        self._on_fader = on_fader
        self._on_mute = on_mute
        self._on_solo = on_solo
        self._on_name = on_name
        self._on_color = on_color
        self._muted = False
        self._soloed = False
        self._default_name = name_default or label_text
        self._name = self._default_name
        self._editing_name = False
        self._color = 0                        # scribble colour index 0-15
        self._color_menu = None                # built on first right-click
        self._menu_color_var = None

        # The card lights up slightly while the mouse hovers over it.
        self.bind("<Enter>", lambda _e: self.configure(
            highlightbackground=_shade(COL_CARD_EDGE, 0.25)))
        self.bind("<Leave>", lambda _e: self.configure(
            highlightbackground=COL_CARD_EDGE))

        # --- colour identity bar (follows the scribble colour) -----------
        self.accent_bar = tk.Frame(self, bg=COL_SEP, height=3)
        self.accent_bar.pack(fill="x", pady=(0, 5))

        # --- name label ---------------------------------------------------
        header_fg = COL_ACCENT if is_main else COL_TEXT
        self.header = tk.Label(
            self, text=label_text, font=FONT_BOLD, bg=COL_STRIP, fg=header_fg
        )
        self.header.pack(fill="x", pady=(0, 4))
        # Double-clicking the label (CH01 ... CH18) opens the channel
        # editor window - only the MIXER tab passes that callback.
        self._on_header = on_header
        if on_header is not None:
            self.header.configure(cursor="hand2")
            self.header.bind("<Double-Button-1>", self._open_editor)

        # --- fader + level meter side by side ----------------------------
        # DCA strips pass has_meter=False: the X AIR meter blob has no
        # DCA levels, so the fader simply fills the whole row.
        fader_row = tk.Frame(self, bg=COL_STRIP)
        fader_row.pack(fill="x")
        self.fader = FaderWidget(fader_row, on_change=self._fader_changed)
        self.fader.pack(side="left", fill="x", expand=True)
        self.meter = None
        if has_meter:
            self.meter = MeterWidget(fader_row, height=FADER_HEIGHT)
            self.meter.pack(side="left", fill="y", padx=(5, 1))

        # --- value readout (mono "LED" numbers under the fader) ----------
        self.value_label = tk.Label(
            self, text="  -%", font=FONT_MONO_BOLD, bg=COL_STRIP,
            fg=COL_ACCENT
        )
        self.value_label.pack(fill="x", pady=(2, 4))

        # --- MUTE button (underneath the fader) ---------------------------
        self.mute_btn = tk.Button(
            self, text="MUTE", font=FONT_BTN, bd=0, relief="raised",
            cursor="hand2", command=self._toggle_mute,
        )
        self.mute_btn.pack(fill="x", pady=(0, 2), ipady=3)

        # --- SOLO button (underneath the fader) ---------------------------
        self.solo_btn = tk.Button(
            self, text="SOLO", font=FONT_BTN, bd=0, relief="raised",
            cursor="hand2", command=self._toggle_solo,
        )
        self.solo_btn.pack(fill="x", ipady=3)

        # --- scribble name field (underneath SOLO) ------------------------
        # Shows the channel name ("1" ... "18" by default).  The field is
        # read-only until the user double-clicks it; Enter (or leaving the
        # field) stores the new name, Escape aborts the edit.
        self.name_var = tk.StringVar(value=self._default_name)
        self.name_entry = tk.Entry(
            self, textvariable=self.name_var, font=FONT_SMALL, width=8,
            justify="center", bd=0, relief="flat", state="readonly",
            readonlybackground=COL_FIELD, bg=COL_FIELD, fg=COL_TEXT,
            insertbackground=COL_TEXT, highlightthickness=1,
            highlightbackground=COL_CARD_EDGE, highlightcolor=COL_ACCENT,
        )
        self.name_entry.pack(fill="x", pady=(6, 0), ipady=3)
        self.name_entry.bind("<Double-Button-1>", self._begin_name_edit)
        self.name_entry.bind("<Return>", self._commit_name_edit)
        self.name_entry.bind("<FocusOut>", self._commit_name_edit)
        self.name_entry.bind("<Escape>", self._cancel_name_edit)
        # Right-click (and Ctrl+click for macOS) opens the colour menu.
        self.name_entry.bind("<Button-3>", self._popup_color_menu)
        self.name_entry.bind("<Control-Button-1>", self._popup_color_menu)
        self._apply_name_color()

        self._refresh_buttons()

        # Wheel events over label/buttons scroll the fader bank; over the
        # fader itself they change the level (FaderWidget handles that).
        if on_wheel is not None:
            for widget in (self, self.header, self.value_label,
                           self.mute_btn, self.solo_btn, self.name_entry):
                widget.bind("<MouseWheel>", on_wheel)
                widget.bind("<Button-4>", on_wheel)
                widget.bind("<Button-5>", on_wheel)

    # -- fader -------------------------------------------------------------

    def _open_editor(self, _event=None) -> None:
        """Double-click on the header label -> open the channel editor."""
        if self._on_header is not None:
            self._on_header(self.strip)

    def _fader_changed(self, value: float) -> None:
        """Called for every user driven fader movement."""
        self._show_value(value)
        self._on_fader(self.strip, value)

    def set_fader(self, value: float) -> None:
        """Apply a fader position that came from the mixer."""
        self.fader.set_value(value)
        self._show_value(self.fader.value())

    def _show_value(self, value: float) -> None:
        self.value_label.configure(text=f"{value * 100:3.0f}%")

    # -- MUTE --------------------------------------------------------------

    def _toggle_mute(self) -> None:
        """Local button press: flip the state and report it upwards."""
        self.set_mute(not self._muted)          # optimistic update
        self._on_mute(self.strip, self._muted)

    def set_mute(self, muted: bool) -> None:
        """Apply a mute state received from the mixer."""
        if muted == self._muted:
            return
        self._muted = muted
        self.fader.set_muted(muted)        # groove fill turns red
        self._refresh_buttons()

    def is_muted(self) -> bool:
        return self._muted

    # -- SOLO --------------------------------------------------------------

    def _toggle_solo(self) -> None:
        self.set_solo(not self._soloed)
        self._on_solo(self.strip, self._soloed)

    def set_solo(self, soloed: bool) -> None:
        """Apply a solo state received from the mixer."""
        if soloed == self._soloed:
            return
        self._soloed = soloed
        self._refresh_buttons()

    def is_soloed(self) -> bool:
        return self._soloed

    # -- scribble name (double-click to rename) ----------------------------

    def name(self) -> str:
        """The name currently shown in the scribble field."""
        return self._name

    def is_editing_name(self) -> bool:
        return self._editing_name

    def set_name(self, name: str) -> None:
        """Apply a name received from the mixer (state load / feedback).

        Names that are empty on the mixer do not overwrite the local
        default label ("1" ... "18" / "MAIN LR"), and nothing is applied
        while the user is typing in the field.
        """
        if self._editing_name:
            return                          # never overwrite active typing
        name = (name or "").strip()
        if not name or name == self._name:
            return                          # empty or unchanged
        self._name = name
        self.name_var.set(name)

    def _begin_name_edit(self, _event=None) -> None:
        """Double-click: unlock the field and select the whole text."""
        self._editing_name = True
        self.name_entry.configure(state="normal")
        self.name_entry.focus_set()
        self.name_entry.select_range(0, "end")

    def _commit_name_edit(self, _event=None) -> None:
        """Store the typed name (Enter / focus change) and report it."""
        if not self._editing_name:
            return
        self._editing_name = False
        self.name_entry.configure(state="readonly")

        name = self.name_var.get().strip()[:MAX_NAME_LEN]
        if not name:
            # Clearing the field restores the default label; the mixer
            # keeps its previous name in that case.
            name = self._default_name
        self.name_var.set(name)
        self.name_entry.selection_clear()

        if name != self._name:
            self._name = name
            self._on_name(self.strip, name)

    def _cancel_name_edit(self, _event=None) -> None:
        """Escape: abort the edit and keep the previous name."""
        if not self._editing_name:
            return
        self._editing_name = False
        self.name_var.set(self._name)
        self.name_entry.configure(state="readonly")
        self.name_entry.selection_clear()

    # -- scribble name colour (right-click to choose) ----------------------

    def color_index(self) -> int:
        """Current scribble colour index (0-15) of this strip."""
        return self._color

    def set_color(self, index: int) -> None:
        """Apply a scribble colour (state load / mixer feedback / menu)."""
        try:
            index = max(0, min(15, int(index)))
        except (TypeError, ValueError):
            return
        if index == self._color:
            return
        self._color = index
        if self._menu_color_var is not None:
            self._menu_color_var.set(index)
        self._apply_name_color()

    def _default_accent(self) -> str:
        """Fader groove colour of this strip without a scribble colour."""
        if self._is_main:
            return COL_ACCENT
        return _mix(COL_ACCENT, COL_STRIP, 0.62)   # dimmed steel blue

    def _apply_name_color(self) -> None:
        """Paint the name field according to the current colour index.

        Colours 0-7 are drawn as coloured text on the dark field; the
        inverted variants 8-15 imitate the mixer by drawing black text
        on a coloured field.  The chosen colour also paints the identity
        bar above the strip and the fader groove fill, so a strip can be
        recognised at a glance.
        """
        _label, hex_colour = SCRIBBLE_COLOR_BY_INDEX.get(
            self._color, ("OFF", None)
        )
        inverted = self._color >= 8
        if hex_colour and inverted:
            # "#14171c" = the near-black scribble ink the mixer uses.
            self.name_entry.configure(
                readonlybackground=hex_colour, bg=hex_colour, fg="#14171c"
            )
        elif hex_colour:
            self.name_entry.configure(
                readonlybackground=COL_FIELD, bg=COL_FIELD, fg=hex_colour
            )
        else:                                   # OFF -> plain field
            self.name_entry.configure(
                readonlybackground=COL_FIELD, bg=COL_FIELD, fg=COL_TEXT
            )
        # colour identity: bar above the strip + fader groove fill
        self.accent_bar.configure(
            bg=hex_colour or (COL_ACCENT if self._is_main else COL_SEP)
        )
        self.fader.set_accent(hex_colour or self._default_accent())

    def _ensure_color_menu(self) -> tk.Menu:
        """Build the colour popup once (16 entries + header) on demand."""
        if self._color_menu is not None:
            return self._color_menu

        menu = tk.Menu(self, tearoff=0, bg=COL_STRIP, fg=COL_TEXT,
                       activebackground=COL_ACCENT,
                       activeforeground=COL_ACCENT_DK,
                       font=FONT_SMALL)
        menu.add_command(label=f"{strip_label(self.strip)} name colour:",
                         state="disabled")
        menu.add_separator()
        self._menu_color_var = tk.IntVar(value=self._color)
        for index, label, _hex_colour in SCRIBBLE_COLORS:
            menu.add_radiobutton(
                label=label, variable=self._menu_color_var, value=index,
                command=lambda i=index: self._choose_color(i),
            )
        self._color_menu = menu
        return menu

    def _popup_color_menu(self, event) -> None:
        """Right-click on the name field: show the colour choices."""
        menu = self._ensure_color_menu()
        self._menu_color_var.set(self._color)   # tick the active colour
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _choose_color(self, index: int) -> None:
        """Colour picked in the menu: apply locally and send it."""
        if index == self._color:
            return                              # nothing changed
        self.set_color(index)                   # optimistic local update
        self._on_color(self.strip, index)

    # -- button colours ----------------------------------------------------

    def _refresh_buttons(self) -> None:
        """Recolour MUTE/SOLO according to their current state."""
        if self._muted:
            mute_style = dict(bg=COL_RED, fg="#ffffff",
                              activebackground=COL_RED_HL,
                              activeforeground="#ffffff", relief="sunken")
        else:
            mute_style = dict(bg=COL_BTN_OFF, fg=COL_TEXT_DIM,
                              activebackground=COL_BTN_OFF_HL,
                              activeforeground=COL_TEXT, relief="raised")
        self.mute_btn.configure(**mute_style)

        if self._soloed:
            solo_style = dict(bg=COL_YELLOW, fg="#241c00",
                              activebackground=COL_YELLOW_HL,
                              activeforeground="#241c00", relief="sunken")
        else:
            solo_style = dict(bg=COL_BTN_OFF, fg=COL_TEXT_DIM,
                              activebackground=COL_BTN_OFF_HL,
                              activeforeground=COL_TEXT, relief="raised")
        self.solo_btn.configure(**solo_style)

        # Dim the value readout while the channel is muted.
        self.value_label.configure(
            fg=COL_TEXT_DIM if self._muted else COL_ACCENT
        )


# ===========================================================================
# 4b. Channel editor window (double-click on a channel label)
# ===========================================================================

class ChannelParam:
    """Bookkeeping for ONE parameter control of the channel editor.

    Holds the Tk variable of a single "/ch/NN/..." address together
    with its value kind and converts between the normalised protocol
    value (0..1), the widget state and the readout text.
    """

    def __init__(self, address, kind, lo, hi, *, var, label_var=None,
                 enum_names=None, fmt=None, widget=None):
        self.address = address
        self.kind = kind        # bool enum lin log send raw muteinv group
        self.lo = lo                    # real range low ("lin"/"log")
        self.hi = hi                    # real range high
        self.var = var      # Tk variable, or a list of 4 for kind "group"
        self.label_var = label_var      # slider readout (or None)
        self.enum_names = enum_names    # name tuple for kind "enum"
        self.fmt = fmt or fmt_plain     # real value -> readout text
        self.widget = widget            # the Tk control (tests / diagnostics)
        self.last_sent = None           # slider echo throttle (0..1)

    # -- mixer -> widget ---------------------------------------------------

    def apply(self, raw) -> None:
        """Display a value that came from the mixer (no OSC is sent)."""
        kind = self.kind
        if kind == "bool":
            self.var.set(1 if _to_bool(raw) else 0)
        elif kind == "muteinv":
            # /mix/on: 1 = active -> the MUTE checkbox must be OFF.
            self.var.set(0 if _to_bool(raw) else 1)
        elif kind == "group":
            # Bitmask: bit 0 = group 1 ... bit 3 = group 4 -> 4 boxes.
            value = int(round(float(raw)))
            for bit, var in enumerate(self.var):
                var.set(1 if value & (1 << bit) else 0)
        elif kind == "enum":
            index = int(round(float(raw)))
            names = self.enum_names or ()
            if 0 <= index < len(names):
                self.var.set(names[index])
            else:
                self.var.set(f"?{index}")       # unexpected mixer value
        elif kind in ("lin", "log"):
            norm = _clamp01(float(raw))
            self.var.set(norm)
            self.refresh_label()
        else:                                   # "send" / "raw" = plain 0..1
            norm = _clamp01(float(raw))
            self.var.set(norm)
            self.refresh_label()

    def refresh_label(self) -> None:
        """Re-render the slider readout from the current variable value."""
        if self.label_var is None:
            return
        norm = _clamp01(float(self.var.get() or 0.0))
        if self.kind in ("lin", "log"):
            self.label_var.set(
                self.fmt(norm_to_real(self.kind, self.lo, self.hi, norm)))
        else:
            self.label_var.set(fmt_percent(norm * 100.0))

    # -- widget -> mixer ---------------------------------------------------

    def raw(self):
        """Current widget state as the value that goes to the mixer."""
        kind = self.kind
        if kind == "bool":
            return 1 if int(self.var.get()) else 0
        if kind == "muteinv":
            # MUTE checkbox ON -> /mix/on 0 (muted)
            return 0 if int(self.var.get()) else 1
        if kind == "group":
            # Recombine the 4 switches into the bitmask (bit 0 = group 1).
            return sum(1 << bit for bit, var in enumerate(self.var)
                       if int(var.get()))
        if kind == "enum":
            try:
                return self.enum_names.index(str(self.var.get()))
            except (ValueError, AttributeError):
                return None
        return _clamp01(float(self.var.get()))


def _darken_combo_popdown(combo: ttk.Combobox) -> None:
    """Paint a combobox drop-down list dark grey.

    The ttk combobox keeps its own hidden popdown window holding a plain
    tk.Listbox, which Tk fills with the light system colours (white) the
    first time the menu opens - the style options of the closed combobox
    do NOT reach it.  Forcing the window into existence here recolours
    the list before the user ever sees it; the colours stay applied on
    every later post, and the listbox selection uses the accent colour
    like the other popups of this application.
    """
    try:
        popdown = combo.tk.eval(f"ttk::combobox::PopdownWindow {combo}")
        combo.tk.eval(f"{popdown} configure -background {COL_STRIP}")
        # the frame holding listbox + scrollbar is a ttk.Frame
        combo.tk.eval(f"::ttk::style configure Popdown.TFrame "
                      f"-background {COL_STRIP}")
        combo.tk.eval(f"{popdown}.f configure -style Popdown.TFrame")
        combo.tk.eval(
            f"{popdown}.f.l configure -background {COL_STRIP} "
            f"-foreground {COL_TEXT} -selectbackground {COL_ACCENT} "
            f"-selectforeground {COL_ACCENT_DK}")
    except tk.TclError:                 # ancient Tk without the helper
        pass


class ChannelEditWindow(tk.Toplevel):
    """Editor for ONE input channel (CH01 ... CH18).

    Opened by double-clicking the channel label on the MIXER tab.  The
    tabs show preamp gain, pan and input source, noise gate, the 4-band
    equalizer, the compressor, all sends (AUX 1-6, FX 1-4) plus the
    Main LR output level / routing / mute, and the DCA / mute group
    assignment switches.

    Two-way behaviour: every parameter is queried when the window opens
    (missing answers are re-asked twice - see _pending/_retry_pending),
    mixer feedback (echoes and remote changes) keeps the widgets live,
    and each user action is written to the mixer with OSC.  MixerGUI
    keeps a reference to the (single) open window in .channel_dialog.
    """

    def __init__(self, app: "MixerGUI", channel: int):
        super().__init__(app.root, bg=COL_BG)
        self.app = app
        self.channel = channel
        self._silent = False            # True while mixer data is applied
        self._controls: dict = {}       # OSC address -> ChannelParam
        # Query bookkeeping: ~60 UDP queries are fired at once when the
        # window opens and a real mixer occasionally drops one of them,
        # so every address that was queried goes into this set, is
        # removed by the arriving answer and is re-asked twice (0.7 s
        # apart) while it is still missing.
        self._pending: set = set()      # queried, not answered yet
        self._retries_left = 0
        self._retry_after = None        # Tk after() id of the retry timer
        self._status_var = tk.StringVar(value="")

        self.title(f"{strip_label(channel)} - channel editor")
        self.geometry("780x660")
        self.minsize(740, 640)
        self.transient(app.root)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Dark widget styles (clam honours these options) -------------------
        # NOTE: ttk.Scale must keep its default style - the theme looks its
        # layout up as "Horizontal.<style>", which does not exist for
        # custom style names.  The colours are set on the base style;
        # the main window contains no other ttk.Scale.
        style = ttk.Style(self)
        style.configure("TScale", background=COL_ACCENT,
                        troughcolor=COL_FIELD)
        style.map("TScale",
                  background=[("active", _shade(COL_ACCENT, 0.30)),
                              ("pressed", _shade(COL_ACCENT, -0.20))])
        style.configure("Dialog.TCheckbutton", background=COL_BG,
                        foreground=COL_TEXT, font=FONT)
        style.map("Dialog.TCheckbutton",
                  background=[("active", COL_BAR)],
                  foreground=[("active", COL_TEXT)])
        # The combobox: clam's own state map paints the *readonly* field
        # light grey (#dcdad5) and its bevel light, which turns our light
        # text invisible.  A map on THIS derived style wins over the base
        # theme, so every state the field passes through stays dark.
        style.configure("Dialog.TCombobox", fieldbackground=COL_FIELD,
                        background=COL_BTN_OFF, foreground=COL_TEXT,
                        arrowcolor=COL_TEXT,
                        bordercolor=COL_SEP, lightcolor=COL_FIELD,
                        darkcolor=COL_BAR)
        style.map("Dialog.TCombobox",
                  fieldbackground=[("readonly", COL_FIELD),
                                   ("readonly focus", COL_FIELD),
                                   ("disabled", COL_BTN_OFF)],
                  foreground=[("readonly", COL_TEXT),
                              ("readonly focus", COL_TEXT),
                              ("disabled", COL_TEXT_DIM)],
                  background=[("active", COL_BTN_OFF_HL),
                              ("pressed", COL_ACCENT_DK)],
                  arrowcolor=[("disabled", COL_GREY)],
                  bordercolor=[("focus", COL_ACCENT)])
        style.configure("Dialog.TLabelframe", background=COL_BG,
                        foreground=COL_TEXT, bordercolor=COL_SEP)
        style.configure("Dialog.TLabelframe.Label", background=COL_BG,
                        foreground=COL_ACCENT, font=FONT_BTN)

        # accent strip along the top edge of the window
        tk.Frame(self, bg=COL_ACCENT, height=4).pack(fill="x")

        self._build_header()
        self.notebook = ttk.Notebook(self)   # kept for tests / diagnostics
        _apply_notebook_style(style, self.notebook)
        # keep the tabs dark after every selection change (clam glitch)
        self.notebook.bind(
            "<<NotebookTabChanged>>",
            lambda _e: _apply_notebook_style(style, self.notebook),
        )
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        notebook = self.notebook
        self._build_input_tab(notebook)
        self._build_gate_tab(notebook)
        self._build_eq_tab(notebook)
        self._build_dyn_tab(notebook)
        self._build_sends_tab(notebook)
        self._build_groups_tab(notebook)

        self._query_all()               # read the live values from the mixer

    # ------------------------------------------------------------------
    # window pieces
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=COL_BG)
        header.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(header, text=f"CH{self.channel:02d}",
                 font=("Segoe UI", 15, "bold"), bg=COL_BG,
                 fg=COL_ACCENT).pack(side="left")
        strip = self.app.strips.get(self.channel)
        if strip is not None:
            tk.Label(header, text=f"- {strip.name()}", font=FONT, bg=COL_BG,
                     fg=COL_TEXT).pack(side="left", padx=(8, 0))
        if self.app.state != CONNECTED:
            tk.Label(header, text="not connected - showing defaults",
                     font=FONT_SMALL, bg=COL_BG, fg=COL_AMBER).pack(
                side="right")

        # Second header line: live feedback of the initial value query
        # ("reading ... -> (blank) when all answers arrived, or a warning
        # after the retries were used up).
        status_row = tk.Frame(self, bg=COL_BG)
        status_row.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(status_row, textvariable=self._status_var,
                 font=FONT_SMALL, bg=COL_BG, fg=COL_AMBER,
                 anchor="w").pack(fill="x")
        tk.Frame(self, bg=COL_SEP, height=1).pack(fill="x", padx=14,
                                                  pady=(2, 6))

    def _build_input_tab(self, notebook) -> None:
        tab = tk.Frame(notebook, bg=COL_BG)
        notebook.add(tab, text="Input")
        # Preamp gain: the only editor value that is not a /ch/NN/...
        # parameter (it lives at /headamp/NN/gain), hence its own address.
        self._add_scale(tab, "gain", "Preamp gain", "lin",
                        HEADAMP_GAIN_LO, HEADAMP_GAIN_HI, fmt_db_signed,
                        address=gain_address(self.channel))
        self._add_scale(tab, "mix/pan", "Pan", "lin",
                        -100.0, 100.0, fmt_pan)
        self._add_enum(tab, "config/insrc", "Input source",
                       source_choices(self.app.channel_count), width=16)
        tk.Label(
            tab,
            text=("Selects which input feeds this channel.\n"
                  "IN 01 ... match the numbered preamps of the mixer,\n"
                  "L (AUX) / R (AUX) are the AUX inputs of the XR16."),
            font=FONT_SMALL, bg=COL_BG, fg=COL_TEXT_DIM, justify="left",
        ).pack(anchor="w", padx=14, pady=(14, 0))

    def _build_gate_tab(self, notebook) -> None:
        tab = tk.Frame(notebook, bg=COL_BG)
        notebook.add(tab, text="Gate")
        self._add_check(tab, "gate/on", "Noise gate ON")
        self._add_enum(tab, "gate/mode", "Mode", GATE_MODES)
        self._add_scale(tab, "gate/thr", "Threshold", "lin",
                        -80.0, 0.0, fmt_db)
        self._add_scale(tab, "gate/range", "Range", "lin",
                        3.0, 60.0, fmt_db0)
        self._add_scale(tab, "gate/attack", "Attack", "lin",
                        0.0, 120.0, fmt_ms)
        self._add_scale(tab, "gate/hold", "Hold", "log",
                        0.02, 2000.0, fmt_ms)
        self._add_scale(tab, "gate/release", "Release", "log",
                        5.0, 4000.0, fmt_ms)
        self._add_enum(tab, "gate/keysrc", "Key source", KEY_SOURCES)
        self._add_check(tab, "gate/filter/on", "Key filter ON")
        self._add_enum(tab, "gate/filter/type", "Filter type", FILTER_TYPES)
        self._add_scale(tab, "gate/filter/f", "Filter freq", "log",
                        20.0, 20000.0, fmt_hz)

    def _build_eq_tab(self, notebook) -> None:
        tab = tk.Frame(notebook, bg=COL_BG)
        notebook.add(tab, text="EQ")
        self._add_check(tab, "eq/on", "Equalizer ON")
        grid = tk.Frame(tab, bg=COL_BG)
        grid.pack(fill="both", expand=True, padx=6, pady=6)
        labels = {1: "Band 1 (low)", 2: "Band 2 (low-mid)",
                  3: "Band 3 (high-mid)", 4: "Band 4 (high)"}
        for band in (1, 2, 3, 4):
            cell = tk.Frame(grid, bg=COL_BG)
            cell.grid(row=(band - 1) // 2, column=(band - 1) % 2,
                      sticky="nsew", padx=4, pady=4)
            box = ttk.Labelframe(cell, text=labels[band],
                                 style="Dialog.TLabelframe")
            box.pack(fill="both", expand=True)
            self._add_enum(box, f"eq/{band}/type", "Type", EQ_TYPES,
                           width=10)
            self._add_scale(box, f"eq/{band}/f", "Freq", "log",
                            20.0, 20000.0, fmt_hz)
            self._add_scale(box, f"eq/{band}/g", "Gain", "lin",
                            -15.0, 15.0, fmt_db_signed)
            self._add_scale(box, f"eq/{band}/q", "Q", "log",
                            10.0, 0.3, fmt_q)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)

    def _build_dyn_tab(self, notebook) -> None:
        tab = tk.Frame(notebook, bg=COL_BG)
        notebook.add(tab, text="Comp")
        self._add_check(tab, "dyn/on", "Compressor ON")
        self._add_enum(tab, "dyn/mode", "Mode", DYN_MODES)
        self._add_enum(tab, "dyn/det", "Detector", DYN_DETECTORS)
        self._add_enum(tab, "dyn/env", "Envelope", DYN_ENVELOPES)
        self._add_scale(tab, "dyn/thr", "Threshold", "lin",
                        -60.0, 0.0, fmt_db)
        self._add_enum(tab, "dyn/ratio", "Ratio", DYN_RATIOS, width=10)
        self._add_scale(tab, "dyn/knee", "Knee", "lin", 0.0, 5.0, fmt_db)
        self._add_scale(tab, "dyn/mgain", "Makeup gain", "lin",
                        0.0, 24.0, fmt_db)
        self._add_scale(tab, "dyn/attack", "Attack", "lin",
                        0.0, 120.0, fmt_ms)
        self._add_scale(tab, "dyn/hold", "Hold", "log",
                        0.02, 2000.0, fmt_ms)
        self._add_scale(tab, "dyn/release", "Release", "log",
                        5.0, 4000.0, fmt_ms)
        self._add_scale(tab, "dyn/mix", "Mix", "lin", 0.0, 100.0,
                        fmt_percent)
        self._add_enum(tab, "dyn/keysrc", "Key source", KEY_SOURCES)
        self._add_check(tab, "dyn/auto", "Auto gain recovery")
        self._add_check(tab, "dyn/filter/on", "Key filter ON")
        self._add_enum(tab, "dyn/filter/type", "Filter type", FILTER_TYPES)
        self._add_scale(tab, "dyn/filter/f", "Filter freq", "log",
                        20.0, 20000.0, fmt_hz)

    def _build_sends_tab(self, notebook) -> None:
        tab = tk.Frame(notebook, bg=COL_BG)
        notebook.add(tab, text="Sends")

        aux = ttk.Labelframe(tab, text="AUX sends (to Bus 1-6)",
                             style="Dialog.TLabelframe")
        aux.pack(fill="x", padx=10, pady=(10, 4))
        for n in range(1, AUX_SEND_COUNT + 1):
            self._add_scale(aux, f"mix/{n:02d}/level", f"AUX {n}",
                            "send", None, None)

        fx = ttk.Labelframe(tab, text="FX sends (to FX 1-4)",
                            style="Dialog.TLabelframe")
        fx.pack(fill="x", padx=10, pady=4)
        for n in range(1, FX_SEND_COUNT + 1):
            self._add_scale(fx, f"mix/{n + AUX_SEND_COUNT:02d}/level",
                            f"FX {n}", "send", None, None)

        main = ttk.Labelframe(tab, text="Main LR output",
                              style="Dialog.TLabelframe")
        main.pack(fill="x", padx=10, pady=4)
        # The Main level/mute are the strip's own fader + MUTE (they use
        # the same addresses, so strip and window stay in sync).  Pan
        # lives on the Input tab together with the preamp gain.
        self._add_scale(main, "mix/fader", "Level", "send", None, None)
        self._add_check(main, "mix/lr", "Route to Main LR")
        self._add_check(main, "mix/on", "MUTE", invert=True)

    def _build_groups_tab(self, notebook) -> None:
        """DCA and mute group assignment switches of this channel.

        The mixer stores each family as ONE bitmask integer per channel
        ("/ch/NN/grp/dca" and "/ch/NN/grp/mute", int 0-15): bit 0 =
        group 1 ... bit 3 = group 4.  The four checkbuttons of a family
        therefore share a single control; toggling any box recombines
        the mask and writes it back.
        """
        tab = tk.Frame(notebook, bg=COL_BG)
        notebook.add(tab, text="Groups")
        self._add_group_checks(tab, "grp/dca", "DCA groups",
                               tuple(f"DCA {n}" for n in range(1, 5)))
        self._add_group_checks(tab, "grp/mute", "Mute groups",
                               tuple(f"MUTE {n}" for n in range(1, 5)))
        tk.Label(
            tab,
            text=("Assigns this channel to the DCA masters and the mute\n"
                  "groups of the mixer.  The switches follow the console\n"
                  "and are written back as one bitmask per family\n"
                  "(bit 0 = group 1 ... bit 3 = group 4)."),
            font=FONT_SMALL, bg=COL_BG, fg=COL_TEXT_DIM, justify="left",
        ).pack(anchor="w", padx=14, pady=(14, 0))

    # ------------------------------------------------------------------
    # widget helpers
    # ------------------------------------------------------------------

    def _address(self, suffix: str) -> str:
        return channel_param_address(self.channel, suffix)

    def _label_row(self, parent, text: str) -> tk.Frame:
        row = tk.Frame(parent, bg=COL_BG)
        row.pack(fill="x", pady=2, padx=10)
        tk.Label(row, text=text, font=FONT, bg=COL_BG, fg=COL_TEXT,
                 width=15, anchor="w").pack(side="left")
        return row

    def _add_scale(self, parent, suffix, text, kind, lo, hi,
                   fmt=fmt_plain, *, address=None) -> ChannelParam:
        row = self._label_row(parent, text)
        # address overrides the /ch/NN/ prefix (preamp gain uses one).
        address = address or self._address(suffix)
        var = tk.DoubleVar(value=0.5)
        label_var = tk.StringVar(value="")
        # length is only the request - the row stretches to full width.
        scale = ttk.Scale(
            row, from_=0.0, to=1.0, variable=var, orient="horizontal",
            length=140,
            command=lambda _v, a=address: self._on_scale(a),
        )
        scale.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(row, textvariable=label_var, font=FONT_MONO, bg=COL_BG,
                 fg=COL_ACCENT, width=11, anchor="e").pack(side="left")
        control = self._add_control(address, kind, lo, hi, var=var,
                                 label_var=label_var, fmt=fmt, widget=scale)
        control.refresh_label()
        return control

    def _add_check(self, parent, suffix, text, *, invert=False) -> ChannelParam:
        address = self._address(suffix)
        var = tk.IntVar(value=0)
        widget = ttk.Checkbutton(
            parent, text=text, variable=var, style="Dialog.TCheckbutton",
            command=lambda a=address: self._on_user(a),
        )
        widget.pack(anchor="w", pady=2, padx=12)
        return self._add_control(address, "muteinv" if invert else "bool",
                              None, None, var=var, widget=widget)

    def _add_group_checks(self, parent, suffix, text, labels) -> ChannelParam:
        """Four checkbuttons sharing ONE bitmask address (/ch/NN/grp/...).

        A group assignment is a single integer on the wire (bit 0 =
        group 1 ... bit 3 = group 4), so the control keeps one Tk
        variable per switch and combines them in raw()/apply().
        """
        box = ttk.Labelframe(parent, text=text,
                             style="Dialog.TLabelframe")
        box.pack(fill="x", padx=10, pady=(10, 4))
        address = self._address(suffix)
        variables = []
        for label in labels:
            var = tk.IntVar(value=0)
            variables.append(var)
            widget = ttk.Checkbutton(
                box, text=label, variable=var, style="Dialog.TCheckbutton",
                command=lambda a=address: self._on_user(a),
            )
            widget.pack(anchor="w", pady=2, padx=12)
        return self._add_control(address, "group", None, None,
                                 var=variables, widget=box)

    def _add_enum(self, parent, suffix, text, names,
                  *, width=14) -> ChannelParam:
        row = self._label_row(parent, text)
        address = self._address(suffix)
        var = tk.StringVar(value=names[0])
        combo = ttk.Combobox(
            row, textvariable=var, values=list(names), state="readonly",
            width=width, font=FONT, style="Dialog.TCombobox",
        )
        combo.pack(side="left", padx=(0, 8))
        _darken_combo_popdown(combo)     # drop-down list: dark grey, not white
        combo.bind("<<ComboboxSelected>>",
                   lambda _e, a=address: self._on_user(a))
        return self._add_control(address, "enum", None, None, var=var,
                              enum_names=names, widget=combo)

    def _add_control(self, address, kind, lo, hi, *, var, label_var=None,
                  enum_names=None, fmt=None, widget=None) -> ChannelParam:
        control = ChannelParam(address, kind, lo, hi, var=var,
                               label_var=label_var, enum_names=enum_names,
                               fmt=fmt, widget=widget)
        self._controls[address] = control
        return control

    # ------------------------------------------------------------------
    # traffic with the mixer
    # ------------------------------------------------------------------

    def _query_all(self) -> None:
        """Ask the mixer for every value this window can show.

        All addresses are remembered in _pending; the arriving answers
        remove them again (see apply_external) and unanswered ones are
        re-sent twice by _retry_pending.
        """
        if self.app.state != CONNECTED:
            return                       # offline: neutral defaults stay
        self._pending = set()
        for address in channel_editor_addresses(self.channel):
            self._pending.add(address)
            self.app.mixer.send(address)
        self._retries_left = 2
        if self._pending:
            self._status_var.set("reading values from the mixer...")
            self._retry_after = self.after(700, self._retry_pending)

    def _retry_pending(self) -> None:
        """Re-ask for values whose answer is still missing (UDP drop)."""
        self._retry_after = None
        if not self._pending or self.app.state != CONNECTED:
            return                       # everything arrived / went away
        if self._retries_left <= 0:
            # Two retries used up: tell the user some readouts are stale
            # instead of silently showing defaults.
            self._status_var.set("some values were not answered - "
                                 "close and reopen to try again")
            return
        self._retries_left -= 1
        for address in sorted(self._pending):
            self.app.mixer.send(address)
        self._retry_after = self.after(700, self._retry_pending)

    def _send(self, address: str, raw) -> None:
        if self.app.mixer.send(address, raw):
            control = self._controls.get(address)
            if control is not None:
                control.last_sent = raw
        else:
            self.app._show_message(
                f"{strip_label(self.channel)}: '{address.rsplit('/', 1)[-1]}'"
                f" not sent - mixer not connected", COL_AMBER, 2.5)

    def _on_scale(self, address: str) -> None:
        """Slider moved: refresh the readout and write the new value."""
        control = self._controls.get(address)
        if control is None:
            return
        control.refresh_label()
        if self._silent:
            return                       # this move came from the mixer
        raw = control.raw()
        if (control.last_sent is not None
                and abs(raw - control.last_sent) < 0.004):
            return                       # throttle slider traffic
        self._send(address, raw)

    def _on_user(self, address: str) -> None:
        """Combobox selection or checkbutton press -> write the value."""
        if self._silent:
            return
        control = self._controls.get(address)
        if control is None:
            return
        raw = control.raw()
        if raw is None:                  # unknown enum entry - do not send
            return
        self._send(address, raw)

    def apply_external(self, address: str, raw) -> None:
        """Show a mixer value in the matching widget (no OSC is sent).

        Also marks *address* as answered: when the last pending query of
        _query_all has arrived the "reading ..." status line disappears.
        """
        if address in self._pending:
            self._pending.discard(address)
            if not self._pending:
                self._status_var.set("")
        control = self._controls.get(address)
        if control is None:
            return
        self._silent = True
        try:
            control.apply(raw)
        finally:
            self._silent = False

    # -- helpers for tests / diagnostics ----------------------------------

    def value(self, address: str):
        """Current widget value of *address* (int, float or str)."""
        control = self._controls.get(address)
        if control is None:
            return None
        if control.kind == "group":
            return control.raw()        # combined bitmask of the 4 boxes
        return control.var.get()

    def value_text(self, address: str) -> str:
        """Readout text next to the slider of *address*."""
        control = self._controls.get(address)
        if control is None or control.label_var is None:
            return ""
        return control.label_var.get()

    def _on_close(self, *_args) -> None:
        """Window closed (X button or replaced by another channel)."""
        if self._retry_after is not None:
            self.after_cancel(self._retry_after)   # no timer after destroy
            self._retry_after = None
        if self.app.channel_dialog is self:
            self.app.channel_dialog = None
        self.destroy()


# ===========================================================================
# 5. Main application window (GUI logic only - no sockets in here)
# ===========================================================================

def _apply_notebook_style(style: ttk.Style, notebook: ttk.Notebook) -> None:
    """(Re)apply the dark tab style and settle the tab bar.

    Windows + clam repaints a neighbouring tab with the theme's default
    (white) colours after a <<NotebookTabChanged>> event; re-applying
    the style on every change paints it dark again.  update_idletasks
    lets Tk process the repaint immediately instead of showing the
    white tab until the next event.
    """
    style.configure("TNotebook", background=COL_BG, borderwidth=0,
                    tabmargins=(4, 6, 0, 0))
    style.configure("TNotebook.Tab", background=COL_BTN_OFF,
                    foreground=COL_TEXT_DIM, padding=(24, 8),
                    font=FONT_BTN, borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", COL_ACCENT),
                          ("active", COL_BTN_OFF_HL)],
              foreground=[("selected", COL_ACCENT_DK),
                          ("active", COL_TEXT)])
    notebook.update_idletasks()


class MixerGUI:
    """The complete application: connection bar, fader bank, status bar.

    Responsibilities:
      * build and update all widgets,
      * translate user actions into OscMixer commands,
      * drain the OSC event queue with a Tk timer and turn the events
        into widget updates,
      * supervise the link (ping with /xinfo, renew /xremote, detect a
        dead mixer).
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Behringer XR16 / XR18 Remote Control")
        root.configure(bg=COL_BG)
        root.geometry("1340x640")
        root.minsize(780, 540)
        # A crash inside any Tk callback (button, timer, binding) goes
        # to the log file with its traceback instead of only stderr.
        root.report_callback_exception = _report_callback_exception

        # Thread-safe mailbox: OSC thread -> GUI.
        self.events: "queue.Queue" = queue.Queue()

        # Network layer (starts its background receive thread at once).
        # A failure here (no permissions, no network stack) is reported by
        # main() with a message box instead of a traceback.
        self.mixer = OscMixer(self.events)
        self.mixer.start()

        # --- application state -------------------------------------------
        self.state = DISCONNECTED
        self.strips: dict = {}                 # strip key -> StripColumn
        self.rta_cells: dict = {}              # strip key -> RTA meter cell
        self.channel_dialog = None             # open channel editor window
        self._target_ip = None                 # IP the user wants to reach
        self._last_rx = 0.0                    # timestamp of last reply
        self._connect_started = 0.0
        self._next_ping = 0.0
        self._next_xremote = 0.0

        # Configuration file (last mixer IP) and the fader count.  The
        # model reported by /xinfo raises/lowers channel_count when the
        # mixer is connected (XR16 = 16 faders, XR18 = 18 faders).
        self._config = load_config()
        self.channel_count = NUM_CHANNELS      # strips CH1..CHn this model has
        self._active_strips = ALL_STRIPS       # MIXER tab strips of this model
        self._active_set = (set(ALL_STRIPS) | set(BUS_STRIPS)
                            | set(FX_STRIPS) | set(DCA_STRIPS))

        # console state loading (fader positions read from the mixer)
        self._fader_loaded: set = set()        # strips that answered so far
        self._load_deadline = 0.0              # 0 = no load in progress
        self._load_retries = 0
        self._load_reported = False            # success message shown?

        # status texts
        self._link_status = ("Ready - enter the mixer IP and press Connect.",
                             COL_GREY)
        self._temp_msg = None                  # (text, colour, expiry)

        # --- build the interface -----------------------------------------
        self._build_top_bar()
        self._build_tabs()
        self._build_fader_bank()
        self._build_aux_bank()
        self._build_fx_bank()
        self._build_dca_bank()
        self._build_rta_tab()
        self._build_bottom_bar()

        # --- timers --------------------------------------------------------
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_after_id = root.after(POLL_INTERVAL_MS, self._poll_events)
        self._heartbeat_after_id = root.after(HEARTBEAT_MS, self._heartbeat)

    # ------------------------------------------------------------------
    # widget construction
    # ------------------------------------------------------------------

    def _build_top_bar(self) -> None:
        """Brand line, IP entry, connect/reload buttons, LED, status."""
        top = tk.Frame(self.root, bg=COL_BAR)
        top.pack(side="top", fill="x")

        inner = tk.Frame(top, bg=COL_BAR)
        inner.pack(fill="x", padx=14, pady=(10, 8))

        # --- brand ---------------------------------------------------------
        tk.Label(inner, text="XR", font=FONT_TITLE, bg=COL_BAR,
                 fg=COL_ACCENT).pack(side="left")
        tk.Label(inner, text="REMOTE", font=FONT_TITLE, bg=COL_BAR,
                 fg=COL_TEXT).pack(side="left", padx=(3, 0))
        tk.Frame(inner, bg=COL_SEP, width=1).pack(side="left", fill="y",
                                                  padx=14, pady=2)

        tk.Label(inner, text="Mixer IP:", font=FONT, bg=COL_BAR,
                 fg=COL_TEXT_DIM).pack(side="left")

        self.ip_var = tk.StringVar(value=self._saved_ip())
        self.ip_entry = tk.Entry(
            inner, textvariable=self.ip_var, font=FONT_MONO, width=16,
            bg=COL_FIELD, fg=COL_TEXT, insertbackground=COL_TEXT,
            relief="flat", bd=5, highlightthickness=1,
            highlightbackground=COL_CARD_EDGE, highlightcolor=COL_ACCENT,
        )
        self.ip_entry.pack(side="left", padx=(6, 8))
        # Return key = press the Connect button.
        self.ip_entry.bind("<Return>", lambda _e: self._on_connect_button())

        self.connect_btn = tk.Button(
            inner, text="Connect", font=FONT_BTN, bg=COL_ACCENT,
            fg=COL_ACCENT_DK, activebackground=_shade(COL_ACCENT, 0.30),
            activeforeground=COL_ACCENT_DK,
            relief="flat", bd=0, padx=16, pady=4, cursor="hand2",
            command=self._on_connect_button,
        )
        self.connect_btn.pack(side="left", padx=(0, 6))

        # Manually re-read the whole console state (all faders/mutes/solos).
        self.reload_btn = tk.Button(
            inner, text="Reload state", font=FONT_BTN, bg=COL_BTN_OFF,
            fg=COL_TEXT_DIM, activebackground=COL_BTN_OFF_HL,
            activeforeground=COL_TEXT, relief="flat", bd=0, padx=12, pady=4,
            cursor="hand2", command=self._on_reload_state,
        )
        self.reload_btn.pack(side="left", padx=(0, 12))

        # Visual connection indicator (LED with a soft glow ring).
        self.led = tk.Canvas(inner, width=20, height=20, bg=COL_BAR,
                             highlightthickness=0)
        self.led.pack(side="left")
        self._led_halo = self.led.create_oval(1, 1, 19, 19,
                                              fill=_shade(COL_LED_OFF, -0.5),
                                              outline="")
        self._led_dot = self.led.create_oval(5, 5, 15, 15,
                                             fill=COL_LED_OFF, outline="")

        self.status_label = tk.Label(inner, text="", font=FONT, bg=COL_BAR,
                                     fg=COL_GREY, anchor="w")
        self.status_label.pack(side="left", padx=(10, 0), fill="x",
                               expand=True)
        self._render_link_status()

        # hairline under the top bar
        tk.Frame(self.root, bg=COL_SEP, height=1).pack(side="top", fill="x")

    def _build_tabs(self) -> None:
        """Horizontal tab bar: MIXER, AUX, FX, DCA and the RTA bridge."""
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")      # the theme that honours colours
        except tk.TclError:
            pass
        # dark scrollbar for the horizontally scrolling fader bank; the
        # base "TScrollbar" style is configured (not the oriented name)
        # - trough = troughcolor, thumb = background, arrows = arrowcolor
        style.configure("TScrollbar", troughcolor=COL_GROOVE,
                        background=COL_BTN_OFF_HL,
                        arrowcolor=COL_TEXT_DIM, bordercolor=COL_GROOVE)
        style.map("TScrollbar",
                  background=[("active", COL_ACCENT)],
                  arrowcolor=[("active", COL_ACCENT_DK)])

        self.notebook = ttk.Notebook(self.root)
        _apply_notebook_style(style, self.notebook)
        # keep the tabs dark after every selection change (clam glitch)
        self.notebook.bind(
            "<<NotebookTabChanged>>",
            lambda _e: _apply_notebook_style(style, self.notebook),
        )
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        self.mixer_tab = tk.Frame(self.notebook, bg=COL_BG)
        self.aux_tab = tk.Frame(self.notebook, bg=COL_BG)
        self.fx_tab = tk.Frame(self.notebook, bg=COL_BG)
        self.dca_tab = tk.Frame(self.notebook, bg=COL_BG)
        self.rta_tab = tk.Frame(self.notebook, bg=COL_BG)
        self.notebook.add(self.mixer_tab, text="MIXER")
        self.notebook.add(self.aux_tab, text="AUX")
        self.notebook.add(self.fx_tab, text="FX")
        self.notebook.add(self.dca_tab, text="DCA")
        self.notebook.add(self.rta_tab, text="RTA")

    def _build_fader_bank(self) -> None:
        """MIXER tab: 19 strips (CH01..CH18 + Main LR) in a scroll canvas."""
        outer = tk.Frame(self.mixer_tab, bg=COL_BG)
        outer.pack(fill="both", expand=True, padx=10, pady=4)

        self.bank_canvas = tk.Canvas(outer, bg=COL_BG, highlightthickness=0,
                                     bd=0)
        # classic tk.Scrollbar ignores its colours on Windows (native
        # rendering) - the ttk clam scrollbar honours the style above
        xscroll = ttk.Scrollbar(outer, orient="horizontal",
                                command=self.bank_canvas.xview)
        self.bank_canvas.configure(xscrollcommand=xscroll.set)
        self.bank_canvas.pack(side="top", fill="both", expand=True)
        xscroll.pack(side="bottom", fill="x", padx=2)

        self.bank_inner = tk.Frame(self.bank_canvas, bg=COL_BG)
        self._bank_window = self.bank_canvas.create_window(
            (0, 0), window=self.bank_inner, anchor="nw"
        )
        self.bank_inner.bind(
            "<Configure>",
            lambda _e: self.bank_canvas.configure(
                scrollregion=self.bank_canvas.bbox("all")
            ),
        )
        self.bank_canvas.bind("<Configure>", self._on_bank_configure)

        # --- 18 input channels -------------------------------------------
        for number in range(1, NUM_CHANNELS + 1):
            column = StripColumn(
                self.bank_inner, number, label_text=f"CH{number:02d}",
                name_default=default_name_of(number),
                on_fader=self._user_fader,
                on_mute=self._user_mute,
                on_solo=self._user_solo,
                on_name=self._user_name,
                on_color=self._user_color,
                on_wheel=self._scroll_bank,
                on_header=self._open_channel_editor,
            )
            column.pack(side="left", fill="y", padx=4, pady=3)
            self.strips[number] = column

        # --- visual separator --------------------------------------------
        self._separator = tk.Frame(self.bank_inner, bg=COL_SEP, width=3)
        self._separator.pack(side="left", fill="y", padx=10, pady=6)

        # --- main output ---------------------------------------------------
        main_column = StripColumn(
            self.bank_inner, MAIN_STRIP, label_text="MAIN LR", is_main=True,
            name_default=default_name_of(MAIN_STRIP),
            on_fader=self._user_fader,
            on_mute=self._user_mute,
            on_solo=self._user_solo,
            on_name=self._user_name,
            on_color=self._user_color,
            on_wheel=self._scroll_bank,
        )
        main_column.pack(side="left", fill="y", padx=4, pady=3)
        self.strips[MAIN_STRIP] = main_column

        # Remember how much horizontal space the strips really need so the
        # inner frame can never shrink below that (small windows scroll).
        self._bank_needed_width = self.bank_inner.winfo_reqwidth()

    def _apply_channel_count(self, count: int) -> None:
        """Show exactly the channel faders this mixer model has.

        Called when /xinfo reports a model change: an XR16 hides CH17
        and CH18, an XR18 brings them back (packed right before the
        separator so the order CH... | MAIN LR is preserved).
        """
        if count == self.channel_count:
            return
        if count < self.channel_count:
            for number in range(count + 1, self.channel_count + 1):
                self.strips[number].pack_forget()
                self.rta_cells[number]["frame"].pack_forget()
        else:
            for number in range(self.channel_count + 1, count + 1):
                self.strips[number].pack(
                    side="left", fill="y", padx=4, pady=3,
                    before=self._separator,
                )
                # keep the RTA order: CH01..CHn | MAIN | AUX | FX
                self.rta_cells[number]["frame"].pack(
                    side="left", fill="y", padx=3, pady=2,
                    before=self._rta_sep1,
                )
        self.channel_count = count
        self._active_strips = tuple(range(1, count + 1)) + (MAIN_STRIP,)
        self._active_set = (set(self._active_strips) | set(BUS_STRIPS)
                            | set(FX_STRIPS) | set(DCA_STRIPS))
        # the bank became narrower/wider - refresh scroll width and region
        self._bank_needed_width = self.bank_inner.winfo_reqwidth()
        self.bank_canvas.itemconfigure(
            self._bank_window,
            width=max(self.bank_canvas.winfo_width(), self._bank_needed_width),
        )
        self.bank_canvas.configure(scrollregion=self.bank_canvas.bbox("all"))

    def _build_aux_bank(self) -> None:
        """AUX tab: the 6 Bus outputs, each with MUTE and SOLO buttons.

        Bus 1-6 of the X AIR mixers are typically used as monitor/aux
        sends ("/bus/1/..." ... "/bus/6/...", single digit!).  Six strips
        always fit next to each other, so no scrolling canvas is needed
        here - a plain horizontal frame is enough.
        """
        outer = tk.Frame(self.aux_tab, bg=COL_BG)
        outer.pack(fill="both", expand=True)
        for strip in BUS_STRIPS:
            column = StripColumn(
                outer, strip,
                label_text=strip_label(strip),      # "AUX1" ... "AUX6"
                name_default=default_name_of(strip),
                on_fader=self._user_fader,
                on_mute=self._user_mute,
                on_solo=self._user_solo,
                on_name=self._user_name,
                on_color=self._user_color,
            )
            column.pack(side="left", fill="y", padx=6, pady=6)
            self.strips[strip] = column

    def _build_fx_bank(self) -> None:
        """FX tab: the 4 FX returns, each with MUTE and SOLO buttons.

        The four effect processors of the X AIR return their wet signal
        through "/rtn/1/..." ... "/rtn/4/..." (single digit, like the
        buses).  Four strips always fit, so a plain frame is enough.
        """
        outer = tk.Frame(self.fx_tab, bg=COL_BG)
        outer.pack(fill="both", expand=True)
        for strip in FX_STRIPS:
            column = StripColumn(
                outer, strip,
                label_text=strip_label(strip),      # "FX1" ... "FX4"
                name_default=default_name_of(strip),
                on_fader=self._user_fader,
                on_mute=self._user_mute,
                on_solo=self._user_solo,
                on_name=self._user_name,
                on_color=self._user_color,
            )
            column.pack(side="left", fill="y", padx=6, pady=6)
            self.strips[strip] = column

    def _build_dca_bank(self) -> None:
        """DCA tab: the 4 DCA masters, each with MUTE and SOLO buttons.

        DCAs (digit al control associations) group many channels under
        one fader ("/dca/1/..." ... "/dca/4/...", single digit like the
        buses).  They carry fader, mute, solo, name and colour, but no
        channel editor page and no level meter - the "ALL CHANNELS"
        meter blob of the X AIR does not include DCA levels.
        """
        outer = tk.Frame(self.dca_tab, bg=COL_BG)
        outer.pack(fill="both", expand=True)
        for strip in DCA_STRIPS:
            column = StripColumn(
                outer, strip,
                label_text=strip_label(strip),      # "DCA1" ... "DCA4"
                name_default=default_name_of(strip),
                has_meter=False,
                on_fader=self._user_fader,
                on_mute=self._user_mute,
                on_solo=self._user_solo,
                on_name=self._user_name,
                on_color=self._user_color,
            )
            column.pack(side="left", fill="y", padx=6, pady=6)
            self.strips[strip] = column

    # ------------------------------------------------------------------
    # RTA tab (meter bridge)
    # ------------------------------------------------------------------

    def _build_rta_tab(self) -> None:
        """RTA tab: real-time level meter bridge of every mixer source.

        The X AIR pushes one "ALL CHANNELS" meter batch to "/meters/1"
        about every 50 ms: a dB level for every input channel, bus, FX
        return and the Main output.  This tab re-uses that stream - no
        extra subscription - and draws each source as a tall LED bar
        with its short label and a falling peak readout, like the meter
        bridge of a digital console.  Labels follow the scribble colour
        of their strip; CH17/CH18 disappear on an XR16.
        """
        outer = tk.Frame(self.rta_tab, bg=COL_BG)
        outer.pack(fill="both", expand=True, padx=10, pady=6)
        tk.Label(outer, text="REAL-TIME ANALYSER - ALL CHANNELS",
                 font=FONT, bg=COL_BG, fg=COL_TEXT_DIM,
                 anchor="w").pack(anchor="w", pady=(0, 4))
        body = tk.Frame(outer, bg=COL_BG)
        body.pack(fill="both", expand=True)
        self._build_rta_scale(body)

        row = tk.Frame(body, bg=COL_BG)
        row.pack(side="left", fill="y", padx=(4, 0))
        # --- 18 input channels ------------------------------------------
        for number in range(1, NUM_CHANNELS + 1):
            self._add_rta_cell(row, number, f"{number:02d}")
        # --- main output ------------------------------------------------
        self._rta_sep1 = tk.Frame(row, bg=COL_SEP, width=2)
        self._rta_sep1.pack(side="left", fill="y", padx=8, pady=4)
        self._add_rta_cell(row, MAIN_STRIP, "MAIN")
        # --- bus outputs + FX returns ------------------------------------
        self._rta_sep2 = tk.Frame(row, bg=COL_SEP, width=2)
        self._rta_sep2.pack(side="left", fill="y", padx=8, pady=4)
        for strip in BUS_STRIPS:
            self._add_rta_cell(row, strip, strip_label(strip))
        self._rta_sep3 = tk.Frame(row, bg=COL_SEP, width=2)
        self._rta_sep3.pack(side="left", fill="y", padx=8, pady=4)
        for strip in FX_STRIPS:
            self._add_rta_cell(row, strip, strip_label(strip))
        # leftover space on the right keeps the bridge left-aligned
        tk.Frame(row, bg=COL_BG).pack(side="left", fill="both", expand=True)

    def _build_rta_scale(self, parent) -> None:
        """dB ruler on the left edge of the meter bridge."""
        scale = tk.Frame(parent, bg=COL_BG, width=40)
        scale.pack(side="left", fill="y")
        scale.pack_propagate(False)
        canvas = tk.Canvas(scale, width=40, height=RTA_METER_HEIGHT,
                           bg=COL_BG, highlightthickness=0, bd=0)
        canvas.pack()
        for db in (0.0, -6.0, -18.0, -30.0, -45.0, METER_FLOOR_DB):
            norm = (db - METER_FLOOR_DB) / (0.0 - METER_FLOOR_DB)
            y = RTA_METER_HEIGHT - norm * RTA_METER_HEIGHT
            y = max(8.0, min(RTA_METER_HEIGHT - 8.0, y))   # keep text visible
            canvas.create_text(33, y, text=f"{db:.0f}", anchor="e",
                               fill=COL_TEXT_DIM, font=FONT_SMALL)
            canvas.create_line(35, y, 39, y, fill=COL_SEP)

    def _add_rta_cell(self, parent, strip, label_text: str) -> None:
        """One meter bar + label + peak readout of a single source."""
        cell = tk.Frame(parent, bg=COL_BG)
        cell.pack(side="left", fill="y", padx=3, pady=2)
        meter = MeterWidget(cell, height=RTA_METER_HEIGHT,
                            width=RTA_METER_WIDTH, segments=RTA_SEGMENTS)
        meter.pack(pady=(0, 3))
        label = tk.Label(cell, text=label_text, font=FONT_SMALL,
                         bg=COL_BG, fg=COL_TEXT_DIM)
        label.pack()
        peak_var = tk.StringVar(value="")
        tk.Label(cell, textvariable=peak_var, font=FONT_SMALL,
                 bg=COL_BG, fg=COL_TEXT_DIM).pack()
        self.rta_cells[strip] = {
            "frame": cell, "meter": meter, "label": label,
            "peak": peak_var, "shown": None,
        }

    def _sync_rta_color(self, strip) -> None:
        """Tint the RTA label of *strip* with its scribble colour."""
        cell = self.rta_cells.get(strip)
        column = self.strips.get(strip)
        if cell is None or column is None:
            return
        _label, hex_colour = SCRIBBLE_COLOR_BY_INDEX.get(
            column.color_index(), ("OFF", None)
        )
        cell["label"].configure(fg=hex_colour or COL_TEXT_DIM)

    def _build_bottom_bar(self) -> None:
        """Information / warning line at the bottom of the window."""
        bar = tk.Frame(self.root, bg=COL_BG)
        bar.pack(side="bottom", fill="x")
        tk.Frame(bar, bg=COL_SEP, height=1).pack(fill="x")
        row = tk.Frame(bar, bg=COL_BG)
        row.pack(fill="x", padx=14, pady=(6, 8))

        # coloured dot in front of the message (mirrors the text colour)
        self.msg_dot = tk.Canvas(row, width=9, height=9, bg=COL_BG,
                                 highlightthickness=0)
        self.msg_dot.pack(side="left", padx=(0, 9))
        self._msg_dot_item = self.msg_dot.create_oval(1, 1, 8, 8,
                                                      fill=COL_LED_OFF,
                                                      outline="")

        self.msg_label = tk.Label(row, text="", font=FONT_SMALL, bg=COL_BG,
                                  fg=COL_TEXT_DIM, anchor="w")
        self.msg_label.pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------------
    # layout helpers
    # ------------------------------------------------------------------

    def _saved_ip(self) -> str:
        """Mixer IP from the config file (falls back to the default)."""
        candidate = str(self._config.get("mixer_ip", DEFAULT_MIXER_IP)).strip()
        try:
            return str(ipaddress.IPv4Address(candidate))
        except ipaddress.AddressValueError:
            return DEFAULT_MIXER_IP

    def _on_bank_configure(self, event) -> None:
        """Keep the strip frame at least as wide as its content."""
        width = max(event.width, getattr(self, "_bank_needed_width", 0))
        self.bank_canvas.itemconfigure(self._bank_window, width=width)
        self.bank_canvas.configure(scrollregion=self.bank_canvas.bbox("all"))

    def _scroll_bank(self, event) -> None:
        """Mouse wheel scrolling of the horizontal fader bank."""
        delta = getattr(event, "delta", 0)
        if delta:
            self.bank_canvas.xview_scroll(-1 if delta > 0 else 1, "units")
        elif getattr(event, "num", None) == 4:
            self.bank_canvas.xview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.bank_canvas.xview_scroll(1, "units")

    # ------------------------------------------------------------------
    # status displays
    # ------------------------------------------------------------------

    def _set_link_status(self, text: str, colour: str) -> None:
        """Persistent connection status (top bar)."""
        self._link_status = (text, colour)
        self._render_link_status()

    def _render_link_status(self) -> None:
        text, colour = self._link_status
        self.status_label.configure(text=text, fg=colour)

    def _set_led(self, colour: str) -> None:
        # the dot keeps the exact colour (tests read it back); the halo
        # ring behind it is a darkened copy for the glow effect
        self.led.itemconfigure(self._led_halo, fill=_shade(colour, -0.55))
        self.led.itemconfigure(self._led_dot, fill=colour)

    def _show_message(self, text: str, colour: str = COL_TEXT_DIM,
                      seconds: float = 4.0) -> None:
        """Transient message in the bottom bar (errors, hints).

        Every RED message is an error - it is also appended to the log
        file, which is the whole point of the bar's colour scheme.
        """
        if colour == COL_RED_STATUS:
            log_error(text)
        self._temp_msg = (text, colour, time.monotonic() + seconds)
        self.msg_label.configure(text=text, fg=colour)
        self.msg_dot.itemconfigure(self._msg_dot_item, fill=colour)

    # ------------------------------------------------------------------
    # connection handling
    # ------------------------------------------------------------------

    def _on_connect_button(self) -> None:
        """Connect, Cancel or Disconnect - depending on the current state."""
        if self.state == DISCONNECTED:
            self._start_connect()
        else:
            self._stop_connect(user_initiated=True)

    def _start_connect(self) -> None:
        raw = self.ip_var.get().strip()
        try:
            ip = str(ipaddress.IPv4Address(raw))
        except ipaddress.AddressValueError:
            log_error(f'Invalid IP address "{raw}" rejected by the user.')
            messagebox.showerror(
                "Invalid IP address",
                f'"{raw}" is not a valid IPv4 address.\n\n'
                f"Example: {DEFAULT_MIXER_IP}",
            )
            return

        self._target_ip = ip
        try:
            # Selects the mixer and pings it with /xinfo; the console
            # state is queried as soon as the ping is answered.
            self.mixer.connect(ip)
        except (RuntimeError, OSError) as exc:
            self._show_message(str(exc), COL_RED_STATUS, 6.0)
            return

        now = time.monotonic()
        self.state = CONNECTING
        self._connect_started = now
        self._next_ping = now + PING_INTERVAL_S
        self._last_rx = now
        self._reset_state_loading()
        self.connect_btn.configure(text="Cancel")
        self._set_led(COL_AMBER)
        self._set_link_status(f"Connecting to {ip} ...", COL_AMBER)
        self._show_message(
            f"Pinging {ip}:{MIXER_OSC_PORT} via /xinfo ...", COL_TEXT_DIM, 3.0
        )
        # Remember the address for the next start of the application.
        # A read-only folder is not fatal - the app keeps running.
        if update_config(mixer_ip=ip):
            self._config["mixer_ip"] = ip
        else:
            log_warning(f"IP {ip} not stored - cannot write "
                        f"{CONFIG_FILE} (read-only folder?).")
            self._show_message(
                f"IP {ip} not stored - cannot write {CONFIG_FILE.name}.",
                COL_AMBER, 6.0,
            )

    def _stop_connect(self, *, user_initiated: bool) -> None:
        """Leave the connecting/connected state."""
        ip = self._target_ip
        self.mixer.disconnect()
        self._target_ip = None
        self.state = DISCONNECTED
        self._reset_state_loading()
        self.connect_btn.configure(text="Connect")
        # The meters fall silent with the connection - show "no signal"
        # (DCA strips have no meter at all).  The RTA bridge clears too.
        for column in self.strips.values():
            if column.meter is not None:
                column.meter.clear()
        for cell in self.rta_cells.values():
            cell["meter"].clear()
            cell["shown"] = None
            cell["peak"].set("")

        if user_initiated:
            self._set_led(COL_LED_OFF)
            self._set_link_status("Disconnected.", COL_GREY)
            self._show_message("Connection closed by user.", COL_TEXT_DIM, 3.0)
        else:
            self._set_led(COL_RED_STATUS)
            self._set_link_status(f"Connection lost ({ip}).", COL_RED_STATUS)

    # ------------------------------------------------------------------
    # console state loading (fader positions / mute / solo from the mixer)
    # ------------------------------------------------------------------

    def _reset_state_loading(self) -> None:
        """Forget the progress of a previous state load."""
        self._fader_loaded.clear()
        self._load_deadline = 0.0
        self._load_retries = 0
        self._load_reported = False

    def _load_strips(self) -> tuple:
        """All strips whose state is loaded on connect - all tabs.

        The MIXER tab strips depend on the mixer model (XR16 = 16
        channels); the 6 AUX buses, the 4 FX returns and the 4 DCA
        masters are the same on every X AIR model.
        """
        return self._active_strips + BUS_STRIPS + FX_STRIPS + DCA_STRIPS

    def _request_console_state(self) -> None:
        """Ask the mixer for all faders/mutes/solos and track the answers.

        Every parameter is requested with an argument-less OSC message
        ("parameter enquiry"); the mixer echoes its current value back,
        which positions the faders and buttons in the GUI.  Because UDP
        does not guarantee delivery, unanswered parameters are re-queried
        a few times (see _check_state_loading in the heartbeat).
        """
        self._reset_state_loading()
        self._load_deadline = time.monotonic() + STATE_LOAD_TIMEOUT_S
        # Only the strips this model really has are requested; an XR16
        # would never answer CH17/CH18 queries.  The AUX buses are
        # loaded together with the channels.
        self.mixer.query_parameters(self._load_strips())
        self._show_message(
            "Loading console state from the mixer (faders, mutes, solos) ...",
            COL_TEXT_DIM, 3.0,
        )

    def _check_state_loading(self, now: float) -> None:
        """Retry the parameters of the current load that stayed quiet."""
        if not self._load_deadline or now < self._load_deadline:
            return

        missing = [s for s in self._load_strips() if s not in self._fader_loaded]
        if not missing:
            self._load_deadline = 0.0              # everything arrived
            return

        if self._load_retries < STATE_LOAD_RETRIES:
            self._load_retries += 1
            self._load_deadline = now + STATE_LOAD_TIMEOUT_S
            self.mixer.query_strips(missing)       # ask again
            self._show_message(
                f"{len(missing)} parameter(s) did not answer yet "
                f"(retry {self._load_retries}/{STATE_LOAD_RETRIES}): "
                f"{', '.join(strip_label(s) for s in missing)} ...",
                COL_AMBER, 4.0,
            )
        else:
            self._load_deadline = 0.0              # give up for this load
            self._show_message(
                f"No answer from the mixer for: "
                f"{', '.join(strip_label(s) for s in missing)}. "
                f"Press 'Reload state' to try again.", COL_AMBER, 8.0,
            )

    def _on_reload_state(self) -> None:
        """Button: re-read the whole console state from the mixer."""
        if self.state != CONNECTED:
            self._show_message(
                "Reload state: connect to a mixer first.", COL_AMBER, 3.0
            )
            return
        self._request_console_state()

    # ------------------------------------------------------------------
    # timers
    # ------------------------------------------------------------------

    def _poll_events(self) -> None:
        """Drain the OSC mailbox and turn events into widget updates.

        Runs every POLL_INTERVAL_MS in the Tk main thread, therefore all
        widget access happens in the thread that owns them.
        """
        try:
            for _ in range(500):        # do not starve the GUI on bursts
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._dispatch_event(event)
                except Exception as exc:   # keep the GUI alive no matter what
                    self._show_message(f"GUI update error: {exc}",
                                       COL_RED_STATUS, 5.0)

            if (self._temp_msg is not None
                    and self._temp_msg[2] <= time.monotonic()):
                self._temp_msg = None
                self.msg_label.configure(text="", fg=COL_TEXT_DIM)
                self.msg_dot.itemconfigure(self._msg_dot_item,
                                           fill=COL_LED_OFF)

            self._poll_after_id = self.root.after(
                POLL_INTERVAL_MS, self._poll_events
            )
        except tk.TclError:
            # The window was destroyed while the timer was pending - stop.
            pass

    def _heartbeat(self) -> None:
        """Link supervision: ping, renew /xremote, detect a dead mixer."""
        try:
            self._heartbeat_step()
            self._heartbeat_after_id = self.root.after(
                HEARTBEAT_MS, self._heartbeat
            )
        except tk.TclError:
            # The window was destroyed while the timer was pending - stop.
            pass

    def _heartbeat_step(self) -> None:
        now = time.monotonic()

        if self.state == CONNECTING:
            if now - self._connect_started >= CONNECT_TIMEOUT_S:
                ip = self._target_ip
                self._stop_connect(user_initiated=False)
                self._set_link_status(
                    f"No response from mixer at {ip}.", COL_RED_STATUS
                )
                self._show_message(
                    f"Timeout: mixer {ip}:{MIXER_OSC_PORT} did not answer. "
                    f"Check the address and the network connection.",
                    COL_RED_STATUS, 8.0,
                )
            elif now >= self._next_ping:
                # Keep asking until the mixer proves it is alive.
                self.mixer.send("/xinfo")
                self._next_ping = now + PING_INTERVAL_S

        elif self.state == CONNECTED:
            if now - self._last_rx >= LINK_TIMEOUT_S:
                ip = self._target_ip
                self._stop_connect(user_initiated=False)
                self._show_message(
                    f"Connection to {ip} timed out - the mixer stopped "
                    f"answering.", COL_RED_STATUS, 8.0,
                )
            else:
                if now >= self._next_ping:
                    self.mixer.send("/xinfo")     # ping
                    self._next_ping = now + PING_INTERVAL_S
                if now >= self._next_xremote:
                    # Renew the "remote mode" subscription (< 10 s limit),
                    # otherwise the mixer stops sending live feedback.
                    self.mixer.renew_remote()
                    # Meter streams expire the same way - keep them alive.
                    self.mixer.renew_meters()
                    self._next_xremote = now + XREMOTE_RENEW_S
                # Re-query console state parameters that did not answer.
                self._check_state_loading(now)

    # ------------------------------------------------------------------
    # event handling (messages that came from the mixer)
    # ------------------------------------------------------------------

    def _update_meters(self, values) -> None:
        """Distribute one "/meters/1" batch (dB values) to all meters.

        Every strip reads its own index/indices from METER_INDICES;
        stereo strips (FX returns, Main LR) show the louder channel.
        DCA strips have neither an index nor a meter widget (the X AIR
        meter blob does not include DCA levels).  The RTA tab shows the
        same values as one big meter bridge with peak readouts.
        """
        for strip, column in self.strips.items():
            indices = METER_INDICES.get(strip)
            if not indices or column.meter is None:
                continue
            level = max((values[i] for i in indices if i < len(values)),
                        default=METER_FLOOR_DB)
            column.meter.set_db(level)
        for strip, cell in self.rta_cells.items():
            indices = METER_INDICES.get(strip)
            if not indices:
                continue
            level = max((values[i] for i in indices if i < len(values)),
                        default=METER_FLOOR_DB)
            meter = cell["meter"]
            meter.set_db(level)
            # Peak readout with a small deadband so the number falls
            # smoothly instead of flickering on every 50 ms batch.
            peak = meter.peak_db
            shown = cell["shown"]
            if (shown is None
                    or (peak <= METER_FLOOR_DB) != (shown <= METER_FLOOR_DB)
                    or abs(peak - shown) >= 0.25):
                cell["shown"] = peak
                cell["peak"].set("" if peak <= METER_FLOOR_DB
                                 else f"{peak:.1f}")

    def _dispatch_event(self, event) -> None:
        kind = event[0]

        if kind == "xinfo":
            self._last_rx = time.monotonic()
            self._on_xinfo(event[1])
            return

        if kind == "meters":
            # One "/meters/1" batch updates every strip meter.  This does
            # NOT refresh _last_rx: meter streams are fire-and-forget and
            # may continue even when the parameter feedback has died, so
            # they must not mask a broken connection.
            self._update_meters(event[1])
            return

        if kind == "chparam":
            # Detail parameter (gate/EQ/compressor/sends/source/groups) -
            # the event carries (channel, address) and only an open
            # editor window for that channel cares about it.
            self._last_rx = time.monotonic()
            (channel, address), value = event[1], event[2]
            dialog = self.channel_dialog
            if dialog is not None and dialog.channel == channel:
                dialog.apply_external(address, value)
            return

        if kind in ("fader", "mute", "solo", "name", "color"):
            # Any valid reply proves the link is still alive.
            self._last_rx = time.monotonic()
            strip, value = event[1], event[2]
            column = self.strips.get(strip)
            if column is None:
                return
            if kind == "fader":
                column.set_fader(value)
                # An open editor window shows the same Main level.
                dialog = self.channel_dialog
                if dialog is not None and dialog.channel == strip:
                    dialog.apply_external(fader_address(strip), value)
                # Remember that this fader position arrived from the mixer
                # - used to confirm/complete a console state load.  Only
                # strips of the connected model count (an XR16 has no
                # CH17/CH18), so the completion message can compare with
                # len(_active_strips).
                if strip in self._active_set:
                    self._fader_loaded.add(strip)
                if (not self._load_reported
                        and len(self._fader_loaded) >= len(self._load_strips())):
                    self._load_reported = True
                    self._show_message(
                        f"Console state loaded - all {len(self._load_strips())} "
                        f"faders set from the mixer.", COL_GREEN, 5.0,
                    )
            elif kind == "mute":
                column.set_mute(value)
                # ... and the MUTE state of its Main output section
                # (the dialog stores the raw /mix/on sense: 1 = active).
                dialog = self.channel_dialog
                if dialog is not None and dialog.channel == strip:
                    dialog.apply_external(mute_address(strip),
                                          0 if value else 1)
            elif kind == "solo":
                column.set_solo(value)
            elif kind == "name":
                column.set_name(value)          # scribble name from mixer
            else:
                column.set_color(value)         # scribble colour from mixer
                self._sync_rta_color(strip)     # RTA label follows the tint
            return

        if kind == "error":
            self._show_message(event[1], COL_RED_STATUS, 5.0)

    def _on_xinfo(self, args) -> None:
        """Handle the /xinfo reply (ping answer / identification)."""
        strings = [a for a in args if isinstance(a, str)]
        name = strings[1] if len(strings) > 1 else ""
        model = strings[2] if len(strings) > 2 else "mixer"
        version = strings[3] if len(strings) > 3 else "?"

        if self.state == CONNECTING:
            # First answer -> the mixer is there: go online.
            # Verify the model first: the fader count follows it (an
            # XR16 reports "X16" -> 16 channel faders, XR18 -> 18).
            model_note = None
            count = channel_count_from_model(model)
            if count is not None and count != self.channel_count:
                self._apply_channel_count(count)
                model_note = (f"Detected {model} - showing {count} channel "
                              f"faders + Main LR.")
            self.state = CONNECTED
            now = time.monotonic()
            self._next_ping = now + PING_INTERVAL_S
            # 1) switch live feedback on, 2) pull the current console
            # state so every fader/button shows the real mixer values.
            self.mixer.renew_remote()
            self._next_xremote = now + XREMOTE_RENEW_S
            self._request_console_state()
            # Start the real-time level meters for every visible strip.
            self.mixer.subscribe_meters()
            self.connect_btn.configure(text="Disconnect")
            self._set_led(COL_GREEN)
            detail = model + (f" ({name})" if name and name != model else "")
            self._set_link_status(
                f"Connected - {detail} fw {version} @ {self._target_ip}",
                COL_GREEN,
            )
            if model_note:
                self._show_message(model_note, COL_GREEN, 5.0)
        # Further /xinfo answers are only keep-alive pings; their arrival
        # timestamp was already recorded in _dispatch_event().

    # ------------------------------------------------------------------
    # user actions -> mixer
    # ------------------------------------------------------------------

    def _open_channel_editor(self, strip) -> None:
        """Double-click on a channel label -> open the editor window.

        Only channels have an editor; one window exists at a time -
        double-clicking another channel label replaces the open window.
        """
        if not isinstance(strip, int):
            return                      # Main/AUX/FX strips have no editor
        existing = self.channel_dialog
        if existing is not None:
            if existing.channel == strip:
                existing.lift()         # already open - just raise it
                return
            existing._on_close()        # close the previous channel first
        self.channel_dialog = ChannelEditWindow(self, strip)

    def _user_fader(self, strip, value: float) -> None:
        self.mixer.set_fader(strip, value)
        if self.state != CONNECTED:
            self._show_message(
                f"{strip_label(strip)} fader {value * 100:.0f}% - "
                f"not sent (mixer not connected)", COL_AMBER, 2.5,
            )

    def _user_mute(self, strip, muted: bool) -> None:
        self.mixer.set_mute(strip, muted)
        if self.state != CONNECTED:
            self._show_message(
                f"{strip_label(strip)} mute "
                f"{'engaged' if muted else 'released'} - "
                f"not sent (mixer not connected)", COL_AMBER, 2.5,
            )

    def _user_solo(self, strip, soloed: bool) -> None:
        self.mixer.set_solo(strip, soloed)
        if self.state != CONNECTED:
            self._show_message(
                f"{strip_label(strip)} solo "
                f"{'on' if soloed else 'off'} - "
                f"not sent (mixer not connected)", COL_AMBER, 2.5,
            )

    def _user_name(self, strip, name: str) -> None:
        """Rename committed in the scribble field -> send to the mixer."""
        self.mixer.set_name(strip, name)
        if self.state != CONNECTED:
            self._show_message(
                f"{strip_label(strip)} renamed to '{name}' - "
                f"not sent (mixer not connected)", COL_AMBER, 2.5,
            )

    def _user_color(self, strip, index: int) -> None:
        """Colour chosen in the context menu -> send to the mixer."""
        self.mixer.set_color(strip, index)
        if self.state != CONNECTED:
            label = SCRIBBLE_COLOR_BY_INDEX.get(index, (str(index), None))[0]
            self._show_message(
                f"{strip_label(strip)} name colour '{label}' - "
                f"not sent (mixer not connected)", COL_AMBER, 2.5,
            )

    # ------------------------------------------------------------------
    # shutdown
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        """Cleanly stop timers and the network thread, then leave mainloop."""
        for after_id in (self._poll_after_id, self._heartbeat_after_id):
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
        try:
            self.mixer.stop()
        except Exception:                # pragma: no cover
            pass
        self.root.destroy()


# ===========================================================================
# 6. Entry point
# ===========================================================================

def main() -> int:
    """Create the window and run the Tk event loop."""
    setup_logging()              # errors from here on land in LOG_FILE
    _install_excepthook()        # ... including uncaught exceptions

    try:
        root = tk.Tk()
    except tk.TclError as exc:          # e.g. no display available
        log_error(f"Could not open the graphical display: {exc}")
        print(f"Could not open the graphical display: {exc}", file=sys.stderr)
        return 1

    try:
        MixerGUI(root)
    except RuntimeError as exc:
        log_error(f"Startup error: {exc}")
        messagebox.showerror("Startup error", str(exc))
        root.destroy()
        return 1

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
