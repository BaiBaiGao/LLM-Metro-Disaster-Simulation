"""Plot passenger choices and AFC comparisons."""
from pathlib import Path
import argparse
import os
import numpy as np
import pandas as pd

PALETTE=['#0A6DAF','#A72061','#926AAD','#059244','#AC5326','#848385',
         '#D4E5F4','#FBB9BA','#F5EBF4','#C2E3D0','#F6E4D0','#C9C9C9']
CHOICES=['continue_metro','take_shuttle_bus','take_other_surface_bus','take_taxi','take_other_transport','abandon_trip']
LABELS=['Continue metro','Shuttle bus','Other bus','Taxi/Ride-hailing','Other transport','Cancel trip']
COLORS=dict(zip(CHOICES,[PALETTE[i] for i in [0,4,3,1,2,5]]))
LIGHT=dict(zip(CHOICES,[PALETTE[i] for i in [6,10,9,7,8,11]]))
SHORT=dict(zip(CHOICES,['CM','SB','OB','TX','OT','CT']))


def setup(out):
    os.environ['MPLCONFIGDIR']=str(out/'matplotlib_config')
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import font_manager
    font_manager.findfont('Arial',fallback_to_default=False)
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Arial','font.size':12,'text.color':'black','axes.labelcolor':'black',
        'xtick.labelcolor':'black','ytick.labelcolor':'black','axes.edgecolor':PALETTE[5],
        'xtick.color':PALETTE[5],'ytick.color':PALETTE[5],'grid.color':PALETTE[11],
        'axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False,
        'svg.fonttype':'path','pdf.fonttype':42,'figure.facecolor':'white','axes.facecolor':'white'})
    return plt


def save(fig,out,name,dpi):
    fig.canvas.draw()
    for ext in ['svg','pdf','png']:
        fig.savefig(out/f'{name}.{ext}',dpi=dpi,bbox_inches='tight')


def sankey(transitions,ax):
    from matplotlib.patches import Rectangle,PathPatch
    from matplotlib.path import Path as MPath
    stages=[]
    for column in range(3):
        records=transitions[transitions.stage.eq(min(column,1))]
        totals=records.groupby('source' if column<2 else 'target')['count'].sum()
        order=sorted(totals.index,key=lambda key:-totals[key])
        total=totals.sum();gap=.04;y=1.;bounds={}
        scale=.80/total
        for key in order:
            height=totals[key]*scale;bounds[key]=(y-height,y);y-=height+gap
        stages.append((bounds,scale,total))
    xs=[0,.44,.88];width=.12
    for stage in [0,1]:
        left,scale,_=stages[stage];right=stages[stage+1][0]
        offsets_l={k:v[0] for k,v in left.items()};offsets_r={k:v[0] for k,v in right.items()}
        for _,r in transitions[transitions.stage.eq(stage)].iterrows():
            a=offsets_l[r.source];b=offsets_r[r.target];h=r['count']*scale
            x0=xs[stage]+width;x1=xs[stage+1];mid=(x0+x1)/2
            verts=[(x0,a),(mid,a),(mid,b),(x1,b),(x1,b+h),(mid,b+h),(mid,a+h),(x0,a+h),(x0,a)]
            codes=[MPath.MOVETO,MPath.CURVE4,MPath.CURVE4,MPath.CURVE4,MPath.LINETO,MPath.CURVE4,MPath.CURVE4,MPath.CURVE4,MPath.CLOSEPOLY]
            ax.add_patch(PathPatch(MPath(verts,codes),facecolor=LIGHT[r.source],edgecolor='none'))
            offsets_l[r.source]+=h;offsets_r[r.target]+=h
    for col,(bounds,scale,total) in enumerate(stages):
        for key,(lo,hi) in bounds.items():
            ax.add_patch(Rectangle((xs[col],lo),width,hi-lo,color=COLORS[key]))
            if hi-lo>.05:ax.text(xs[col]+width/2,(lo+hi)/2,f'{SHORT[key]}\n{(hi-lo)/scale/total:.1%}',ha='center',va='center',fontsize=10)
        ax.text(xs[col]+width/2,-.06,f'Condition {col+1}',ha='center')
    ax.set(xlim=(-.02,1.02),ylim=(-.08,1.02));ax.axis('off')


def render(data,out,dpi=900):
    data,out=Path(data),Path(out);out.mkdir(parents=True,exist_ok=True)
    if out.drive.lower()=='c:':raise ValueError('Choose a project output directory outside C:.')
    plt=setup(out)
    from matplotlib.ticker import PercentFormatter
    if (data/'A_matrix.csv').exists():
        from matplotlib.colors import ListedColormap
        matrix=pd.read_csv(data/'A_matrix.csv',index_col=0)
        pct=matrix.div(matrix.sum(axis=1).replace(0,np.nan),axis=0)*100
        fig,ax=plt.subplots(figsize=(5.2,4.6),layout='constrained')
        ax.imshow(pct.to_numpy(),cmap=ListedColormap([PALETTE[8],PALETTE[9],PALETTE[3]]),vmin=0,vmax=100)
        for i in range(3):
            for j in range(3):ax.text(j,i,f'{pct.iloc[i,j]:.2f}%\n({matrix.iloc[i,j]})',ha='center',va='center')
        ax.set(xticks=range(3),yticks=range(3),xticklabels=matrix.columns,yticklabels=matrix.index,xlabel='LLM agent',ylabel='Rule agent')
        save(fig,out,'A_paired_matrix',dpi);plt.close(fig)
    if (data/'A_delay.csv').exists():
        from delay_panel import render as delay_render
        with plt.rc_context():
            delay_render(pd.read_csv(data/'A_delay.csv'),{'width_pt':563.3989791870117,'height_pt':262.82000732421875},out,large_text=True,compact=True,dpi=dpi)
    if (data/'B_choice_shares.csv').exists():
        shares=pd.read_csv(data/'B_choice_shares.csv');shares['Affected']=shares.Affected.astype(str).str.lower().isin(['true','1'])
        fig,ax=plt.subplots(figsize=(8,4.8),layout='constrained');bottom=np.zeros(6)
        keys=[(f'condition_{i}',a) for i in [1,2,3] for a in [True,False]]
        for action,label in zip(CHOICES,LABELS):
            values=np.array([shares.loc[shares.Scenario.eq(s)&shares.Affected.eq(a)&shares.Action.eq(action),'Proportion'].sum() for s,a in keys])
            ax.bar(range(6),values,bottom=bottom,color=COLORS[action],label=label);bottom+=values
        ax.set(xticks=range(6),xticklabels=['1 A','1 U','2 A','2 U','3 A','3 U'],ylim=(0,1.23),xlabel='Condition and passenger group',ylabel='Choice share (%)')
        ax.yaxis.set_major_formatter(PercentFormatter(1));ax.legend(ncol=3,loc='upper center',fontsize=10)
        save(fig,out,'B_choice_composition',dpi);plt.close(fig)
        fig,ax=plt.subplots(figsize=(7.5,4.8));sankey(pd.read_csv(data/'B_transitions.csv'),ax)
        save(fig,out,'B_choice_transitions',dpi);plt.close(fig)
        response=pd.read_csv(data/'B_comparison.csv')
        fig,axes=plt.subplots(1,3,figsize=(11,4),sharey=True,layout='constrained')
        for ax,group in zip(axes,['all','affected','unaffected']):
            for j,(series,label,color) in enumerate([('Observed','AFC',PALETTE[0]),('LLM','LLM',PALETTE[4])]):
                rows=response[response.Group.eq(group)&response.Series.eq(series)].sort_values('Scenario')
                ax.bar(np.arange(3)+(j-.5)*.32,rows.Value,.32,color=color,label=label,
                    yerr=rows[['Error_low','Error_high']].to_numpy().T,error_kw={'ecolor':PALETTE[5],'capsize':2})
            ax.set(xticks=range(3),xticklabels=['1','2','3'],ylim=(0,1.25));ax.axhline(1,color=PALETTE[5],ls=':',lw=.7)
            ax.legend();ax.grid(axis='y',lw=.5);ax.set_axisbelow(True)
        axes[0].set_ylabel('Retention / metro-choice share');axes[0].set_xlabel('Operational scenario');axes[2].set_xlabel('Operational scenario')
        save(fig,out,'B_AFC_comparisons',dpi);plt.close(fig)
        st=pd.read_csv(data/'B_stations.csv').sort_values('order')
        fig,ax=plt.subplots(figsize=(7,4.7),layout='constrained');y=np.arange(len(st))
        for delta,col,label,color in [(-.17,'baseline_flow','Normal Sundays',PALETTE[0]),(.17,'observed_flow','Incident day',PALETTE[4])]:
            ax.barh(y+delta,st[col]/1000,.34,label=label,color=color)
        ax.set(yticks=y,yticklabels=st.label,xlabel='Daily entries (thousand)');ax.invert_yaxis();ax.legend(loc='lower right')
        save(fig,out,'B_station_entries',dpi);plt.close(fig)
        seg=pd.read_csv(data/'B_segments.csv').set_index('target').loc[['west','closed','east']]
        fig,ax=plt.subplots(figsize=(4.2,4.7),layout='constrained')
        ax.bar(range(3),seg.Observed,color=[PALETTE[0],PALETTE[5],PALETTE[3]])
        ax.set(xticks=range(3),xticklabels=['West','Suspended\nsection','East'],ylabel='Observed retention ratio',xlabel='Network section',ylim=(0,1.2))
        for i,v in enumerate(seg.Observed):ax.text(i,v+.02,f'{v:.1%}',ha='center')
        save(fig,out,'B_section_retention',dpi);plt.close(fig)
    if (data/'C_choices.csv').exists():
        choices=pd.read_csv(data/'C_choices.csv');times=pd.to_datetime(choices['Decision time'])
        start=pd.Timestamp('2024-09-15 06:00');x=((times-start).dt.total_seconds()/3600).to_numpy()
        labels=['15 Sep\n06:00']+[t.strftime('%d Sep\n%H:%M') for t in times]
        fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True,layout='constrained')
        for ax in axes:
            ax.set(xlim=(0,42.1),ylim=(0,140),xticks=[0,*x],xticklabels=labels)
            ax.axvspan(17,23.5,color=PALETTE[8]);ax.text(20.25,70,'Overnight\nnon-service\nperiod',ha='center',va='center')
            ax.grid(axis='y',lw=.5);ax.set_axisbelow(True);ax.set_xlabel('Decision time (Beijing time)')
            ax.tick_params(labelbottom=True)
        for action,label,color,marker in [('abandon_trip','Cancel trip',PALETTE[5],'s'),('metro_trip','Metro travel',PALETTE[0],'o'),('non_metro_trip','Non-metro travel',PALETTE[4],'^')]:
            y=choices[action+'_pct'];axes[0].plot(x,y,marker=marker,color=color,label=label)
            for xx,yy,n in zip(x,y,choices[action+'_n']):
                dy = -15 if action=='abandon_trip' and yy>15 else 8
                if yy<15 and action=='abandon_trip':dy=25
                if yy<8 and action=='metro_trip':dy=24
                axes[0].annotate(f'{n} ({yy:.1f}%)',(xx,yy),xytext=(0,dy),textcoords='offset points',ha='center',fontsize=9,bbox={'fc':'white','alpha':.55,'ec':'none','pad':.5})
        axes[0].set_ylabel('Choice share (%)');axes[0].legend(ncol=3,loc='upper left')
        for filename,style in [('C_comparison.csv','-'),('C_monday.csv',':')]:
            r=pd.read_csv(data/filename).sort_values('Scenario')
            tt=pd.to_datetime(r.Scenario.str.replace('snapshot_',''),format='%Y%m%d_%H%M');xx=(tt-start).dt.total_seconds()/3600
            for col,label,color,marker in [('Observed','AFC, matched OD' if style=='-' else 'AFC, Monday reference',PALETTE[0] if style=='-' else PALETTE[2],'o'),('LLM','LLM, OD-standardized' if style=='-' else 'LLM, Monday weights',PALETTE[4] if style=='-' else PALETTE[5],'s')]:
                axes[1].plot(xx,r[col]*100,ls=style,color=color,marker=marker,label=label)
                if style=='-':
                    for xxx,yyy in zip(xx,r[col]*100):axes[1].annotate(f'{yyy:.1f}%',(xxx,yyy),xytext=(0,-14),textcoords='offset points',ha='center',fontsize=9,bbox={'fc':'white','alpha':.55,'ec':'none','pad':.5})
            if style=='-':
                for xxx,n in zip(xx,r.OD_N):axes[1].text(xxx,133,f'OD: {n}',ha='center',fontsize=9)
        axes[1].set_ylabel('Retention / metro-choice share (%)');axes[1].legend(ncol=2,loc='upper center',bbox_to_anchor=(.55,.91),fontsize=10)
        save(fig,out,'C_choice_and_AFC_time_series',dpi);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--dpi',type=int,default=900)
    args=parser.parse_args();render(args.data,args.out,args.dpi)
