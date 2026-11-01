#!/usr/bin/env python3
"""Explicitly download the pinned OmniVoice model to a chosen local folder."""
import argparse,json
from pathlib import Path
REVISION='8fb0b754cad788aaefec690cd55c207e8a628f85'
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model-dir',required=True,type=Path);a=p.parse_args()
    from huggingface_hub import snapshot_download
    snapshot_download('mlx-community/OmniVoice-bf16',revision=REVISION,local_dir=a.model_dir,max_workers=4)
    (a.model_dir/'download-receipt.json').write_text(json.dumps(dict(repository='mlx-community/OmniVoice-bf16',revision=REVISION),indent=2),encoding='utf-8')
    print('OmniVoice downloaded. Inference can now run offline.')
