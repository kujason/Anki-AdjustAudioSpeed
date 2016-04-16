import re
import time
import anki.sound

from anki.sound import play
from anki.sound import mplayerQueue, mplayerClear, mplayerEvt
from anki.sound import MplayerMonitor

from anki.hooks import addHook, wrap
from aqt.reviewer import Reviewer
from aqt.utils import showInfo

sound_regex = ur"\[sound:(.*?)\]"

audio_file = ""
audio_speed = 1.0
audio_replay = False

def my_keyHandler(self, evt):
    key = unicode(evt.text())
    global audio_speed, audio_replay
    if key == "0":
        audio_speed = 1.0
    elif key == "[":
        audio_speed = max(0.1, audio_speed - 0.1)
    elif key == "]":
        audio_speed = min(4.0, audio_speed + 0.1)
    
    if key in "0[]":
        if audio_replay:
            play(audio_file)
        elif anki.sound.mplayerManager is not None:
            if anki.sound.mplayerManager.mplayer is not None: 
                anki.sound.mplayerManager.mplayer.stdin.write("af_add scaletempo=stride=10:overlap=0.8\n")
                anki.sound.mplayerManager.mplayer.stdin.write(("speed_set %f \n" % audio_speed))
     
    if key == "p":
        anki.sound.mplayerManager.mplayer.stdin.write("pause\n")
    elif key == "l":
        audio_replay = not audio_replay
        if audio_replay:
            showInfo("Auto Replay ON")
        else:
            showInfo("Auto Replay OFF")

def my_runHandler(self):
    _self = anki.sound.mplayerManager
    global mplayerClear
    _self.mplayer = None
    _self.deadPlayers = []
    while 1:
        anki.sound.mplayerEvt.wait()
        anki.sound.mplayerEvt.clear()
        
        # clearing queue?
        if anki.sound.mplayerClear and _self.mplayer:
            try:
                _self.mplayer.stdin.write("stop\n")
            except:
                # mplayer quit by user (likely video)
                _self.deadPlayers.append(_self.mplayer)
                _self.mplayer = None

        # loop through files to play
        while anki.sound.mplayerQueue:
            # ensure started
            if not _self.mplayer:
                _self.startProcess()
            # pop a file
            try:
                item = anki.sound.mplayerQueue.pop(0)
                _self.mplayer.stdin.write("stop\n")
            except IndexError:
                # queue was cleared by main thread
                continue
            if anki.sound.mplayerClear:
                anki.sound.mplayerClear = False
                extra = ""
            else:
                extra = " 1"
            cmd = 'loadfile "%s"%s\n' % (item, extra)
            
            try:
                _self.mplayer.stdin.write(cmd)
            except:
                # mplayer has quit and needs restarting
                _self.deadPlayers.append(_self.mplayer)
                _self.mplayer = None
                _self.startProcess()
                _self.mplayer.stdin.write(cmd)
            
            if abs(audio_speed - 1.0) > 0.01:
                _self.mplayer.stdin.write("af_add scaletempo=stride=10:overlap=0.8\n")
                _self.mplayer.stdin.write("speed_set %f \n" % audio_speed)
                _self.mplayer.stdin.write("seek 0 1\n")
            
            # if we feed mplayer too fast it loses files
            time.sleep(1)
        # wait() on finished processes. we don't want to block on the
        # wait, so we keep trying each time we're reactivated
        def clean(pl):
            if pl.poll() is not None:
                pl.wait()
                return False
            else:
                return True
        _self.deadPlayers = [pl for pl in _self.deadPlayers if clean(pl)]

def store_file(regex_string):
    global audio_file
    audio_file = regex_string.group(1)
    
def audio_filter(qa_html, qa_type, dummy_fields, dummy_model, dummy_data, dummy_col):
    re.sub(sound_regex, store_file, qa_html)
    return qa_html

Reviewer._keyHandler = wrap(Reviewer._keyHandler, my_keyHandler)
MplayerMonitor.run = my_runHandler

addHook("mungeQA", audio_filter)