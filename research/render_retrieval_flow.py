"""One-slide, plain-language explanation of the offline recommended method."""
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from research.render_similarity_comparison import configure

OUT=PRODUCT/'docs/figures/retrieval_flow_20261021'
INK='#173247'
MUTED='#536b7c'
BLUE='#28669a'
TEAL='#087e82'
GOLD='#a36b12'


def main():
    configure()
    plt.rcParams['svg.fonttype']='none'
    OUT.mkdir(parents=True,exist_ok=True)
    fig=plt.figure(figsize=(16,9),facecolor='white')
    ax=fig.add_axes([0,0,1,1]);ax.set_xlim(0,1600);ax.set_ylim(0,900);ax.axis('off')

    def text(x,y,value,size=16,color=INK,bold=False,**kwargs):
        return ax.text(x,y,value,fontsize=size,color=color,
                       fontweight='bold' if bold else 'normal',va='top',linespacing=1.5,**kwargs)

    def box(x,y,w,h,face='white',edge='#cfdae3',radius=11,lw=1.2):
        p=FancyBboxPatch((x,y),w,h,boxstyle=f'round,pad=0,rounding_size={radius}',
                        facecolor=face,edgecolor=edge,linewidth=lw)
        ax.add_patch(p);return p

    def arrow(x1,y1,x2,y2,color=BLUE):
        ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',
                     mutation_scale=18,linewidth=1.7,color=color))

    text(50,864,'下單前，怎麼找到可參考的歷史案例？',size=29,bold=True)
    text(50,803,'五分K看短線，一小時K看背景，再核對前高低位置。',size=19,color=MUTED)
    box(1302,795,248,63,face='#eff5f8',edge='#d8e3eb')
    text(1320,840,'建議方案｜已完成離線實驗',size=13,color=BLUE,bold=True)
    text(1320,817,'尚未接入網站正式檢索',size=12,color=MUTED)

    xs=[50,437,824,1211]
    titles=['準備兩邊的盤面','整理成同一種格式','先挑可比較的案例','比較後，留下前五']
    for i,(x,title) in enumerate(zip(xs,titles),1):
        box(x,340,340,395,face='#f7fafc')
        box(x+20,671,46,43,face=BLUE if i!=4 else TEAL,edge='none',radius=7)
        text(x+28,704,f'{i:02}',size=17,color='white',bold=True)
        text(x+20,648,title,size=21,bold=True)
    for a,b in zip(xs,xs[1:]):arrow(a+346,533,b-8,533)

    x=xs[0]
    box(x+20,468,300,124)
    text(x+35,574,'歷史案例｜事先整理',size=17,color=BLUE,bold=True)
    text(x+35,535,'取每筆進場前\n已收完的K線',size=16)
    box(x+20,359,300,94,face='#eef7f7',edge='#c9e2e2')
    text(x+35,437,'現在盤面｜提問或下單前',size=15.5,color=TEAL,bold=True)
    text(x+35,404,'選做多／做空，取已收K線',size=15)

    x=xs[1]
    rows=[(526,'五分60根','看進場附近的短線走法'),
          (439,'一小時20根','看較大的趨勢背景'),
          (352,'前高低狀態','最後五分棒對先前20棒')]
    for y,title,body in rows:
        box(x+20,y,300,76,edge='#dbe4ea')
        text(x+34,y+65,title,size=17,color=BLUE,bold=True)
        text(x+34,y+32,body,size=14)

    x=xs[2]
    text(x+22,589,'方向相同',size=18,color=BLUE,bold=True)
    text(x+22,550,'做多找做多；做空找做空',size=15)
    text(x+22,502,'當時已經可用',size=18,color=BLUE,bold=True)
    text(x+22,463,'已平倉，且過保守成熟時間',size=14.5)
    text(x+22,415,'盤面資料完整',size=18,color=BLUE,bold=True)
    text(x+22,376,'不拿同一段重疊行情來比',size=15)

    x=xs[3]
    text(x+22,589,'先看位置情境',size=18,color=TEAL,bold=True)
    text(x+22,550,'同樣突破／跌破／刺穿收回\n或區間內的案例，優先排列',size=14)
    text(x+22,475,'再比兩段完整走勢',size=18,color=TEAL,bold=True)
    text(x+22,436,'逐根比相對漲跌，保留幅度\n先看兩邊中，排名較差的一邊',size=14)
    text(x+22,366,'同一操作群／盤面時點去重',size=14,color=MUTED)

    arrow(xs[-1]+170,330,xs[-1]+170,301,color=TEAL)
    box(50,160,1501,133,face='#edf6f5',edge='#b9d8d4',radius=12)
    text(78,274,'輸出：當前盤面 × 歷史前五組',size=21,color=TEAL,bold=True)
    text(78,224,'五分／一小時對照圖  ＋  相同與不同處  ＋  波動差異',size=18)
    text(1115,237,'供使用者參考與風險檢查',size=16,color=TEAL,bold=True)
    text(1115,202,'沒有足夠同狀態案例時，明列差異',size=12.5,color=MUTED)

    text(51,123,'比較內容是每根收盤的相對變化；前高低狀態另看末棒高低與收盤。',size=14,color=MUTED)
    text(51,88,'手數、盈虧不參與排序；LLM負責解釋。前五是最近參考，足夠相似門檻仍待校準。',size=14,color=MUTED)
    text(1550,35,'Gold Desk｜雙週期路徑＋前高低狀態｜2026-10-21',size=11,color=MUTED,ha='right')

    for ext in ('png','pdf','svg'):
        fig.savefig(OUT/f'相似案例檢索_白話流程圖.{ext}',dpi=300,facecolor='white')
    plt.close(fig)
    print('Exported 4800x2700 PNG, one-page PDF and editable-text SVG')


if __name__=='__main__':main()
