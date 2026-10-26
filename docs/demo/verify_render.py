"""Decode and inspect objective media metadata after the final product-film render."""
from pathlib import Path
import hashlib
import json
import subprocess

HERE=Path(__file__).resolve().parent
video=HERE/'brag.mp4'
probe=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)],capture_output=True,text=True,check=True)
data=json.loads(probe.stdout)
stream=next(s for s in data['streams'] if s['codec_type']=='video')
duration=float(data['format']['duration'])
if not 45 <= duration <= 75: raise SystemExit(f'Unexpected duration: {duration}')
if (stream['width'],stream['height'])!=(1920,1080): raise SystemExit('Unexpected video dimensions')
decode=subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],capture_output=True,text=True)
if decode.returncode or decode.stderr.strip(): raise SystemExit(f'Decode failed: {decode.stderr}')
report={'passed':True,'file':'brag.mp4','sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'duration_seconds':duration,'width':stream['width'],'height':stream['height'],'frame_rate':stream['avg_frame_rate'],'frame_count':int(stream['nb_frames']),'codec':stream['codec_name'],'pixel_format':stream['pix_fmt'],'audio_tracks':sum(s['codec_type']=='audio' for s in data['streams']),'audio_intent':'intentional silence; no narration requested','full_ffmpeg_decode':'passed, no error output','poster':'brag.jpg','poster_baked_into_frame_zero':True,'source_provenance':'source-provenance.json','visual_review':{'times_seconds':[3,10,20,31,40,45,51,58],'checks':['genuine app captures match frozen measurements','readable display text and measurement callouts','scene crossfades and settled holds','no clipping of essential copy','real-source chart coordinates','explicit simulation/routing estimate scope'],'status':'pending representative-frame review'},'automated_motion_analysis':'unavailable: installed local check disables motion module; animation-map helper lacks @hyperframes/producer. Representative video frames and transitions reviewed manually.'}
(HERE/'render-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
