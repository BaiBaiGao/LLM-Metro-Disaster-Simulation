"""Map platform data columns to the simulation input format."""
import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def convert(source, destination, columns):
    frame=pd.read_csv(source)
    names=['time','station_name_mapped','inbound','outbound']
    missing=set(columns)-set(frame.columns)
    if missing:raise ValueError('Missing source columns: '+', '.join(sorted(missing)))
    result=frame[columns].copy(); result.columns=names
    result['time']=pd.to_datetime(result.time,errors='raise')
    result[['inbound','outbound']]=result[['inbound','outbound']].apply(pd.to_numeric,errors='raise')
    if result.isna().any().any() or not np.isfinite(result[['inbound','outbound']]).all().all() or (result[['inbound','outbound']]<0).any().any():
        raise ValueError('Resolve missing or negative source entries before importing.')
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(destination,index=False,encoding='utf-8-sig')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--columns',nargs=4,default=['time','station_name_mapped','inbound','outbound'])
    args=parser.parse_args()
    convert(args.source,args.out,args.columns)
