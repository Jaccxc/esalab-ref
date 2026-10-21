import { Shell, btn, type Me } from '../ui'
import { restartTour } from '../Tour'
import { OrderDemo, SCENARIOS, type Scenario } from './OrderDemo'

const H = ({ children }: { children: string }) => <h2 className="m-0 mt-2 border-b border-ink pb-2 font-tc text-[22px] font-bold">{children}</h2>
const P = ({ children }: { children: React.ReactNode }) => <p className="m-0 font-tc text-[15px] leading-relaxed">{children}</p>
const C = ({ children }: { children: string }) => <code className="bg-mist px-1 font-mono text-[13px]">{children}</code>
const Ex = ({ title, before, after, note, demo, warn }: { title: string; before: string; after: string; note: string; demo: Scenario; warn?: boolean }) => (
  <div className={`flex flex-col gap-2 border p-4 ${warn ? 'border-fail' : 'border-line'}`}>
    <OrderDemo scenario={demo} />
    <span className="font-tc text-sm font-bold">{warn && <span className="mr-2 bg-fail px-1.5 py-0.5 text-xs text-white">常見錯誤</span>}{title}</span>
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-[13px]">
      <span className="text-graphite">本文</span><span>{before}</span>
      <span className="text-graphite">結果</span><span>{after}</span>
    </div>
    <span className="font-tc text-[13px] leading-relaxed text-dim">{note}</span>
  </div>
)

export default function Guide({ me }: { me: Me }) {
  return (
    <Shell me={me} active="guide" wide={false}>
      <div className="flex flex-col gap-7">
        <div className="flex flex-col gap-2">
          <div className="font-mono text-xs tracking-[0.12em] text-graphite">GUIDE</div>
          <div className="flex flex-wrap items-center gap-4"><h1 className="m-0 font-tc text-4xl font-bold">系統怎麼運作</h1>
            <button type="button" className={`${btn.outline} ml-auto`} onClick={restartTour}>重看新手教學</button></div>
          <P>上傳論文 .docx，系統讀出參考文獻、到資料庫查每一筆、停下來讓你確認、核對引用順序、用 LLM 套實驗室 IEEE 格式並審查，最後以 Word 修訂模式寫回。全部可以在 Word 裡逐筆接受或拒絕。</P>
        </div>

        <H>只要貼標題，格式交給系統</H>
        <Ex demo={SCENARIOS.format} title="只要貼標題，格式交給系統" before="清單裡每行貼標題、Google Scholar 複製的字串或 DOI 連結，不排格式" after="每筆查到書目後重寫成實驗室 IEEE 格式，以 Word 修訂寫回；編號不動" note="最常用的情境。清單裡一行一筆，標題、DOI、網址都可以；本文的 [n] 照舊，系統只改清單文字。" />

        <H>三種模式</H>
        <ul className="m-0 flex list-none flex-col gap-2 p-0 font-tc text-[15px] leading-relaxed">
          <li><b>智慧模式</b>（預設）：修正既有 <C>[n]</C> 條目，也加入你輸入的新書目。新書目若已經在清單裡，不重複新增，本文的 <C>[+k]</C> 會自動換成既有編號。</li>
          <li><b>修正模式</b>：只修既有條目，不新增。</li>
          <li><b>新增模式</b>：只加新書目，既有條目完全不碰。</li>
        </ul>

        <H>查書目：輸入什麼、查到哪裡</H>
        <P>系統只認「一筆一段、開頭是 <C>[n]</C>」的清單；Word 自動編號的 <C>[n]</C> 也可以，寫回時會改成手打。讀不出來時工作會停在「讀取條目」問你：勾出屬於清單的段落，或貼成一行一筆（可先交給 LLM 初排），系統加上編號後再繼續。</P>
        <P>每筆條目先從文字裡抓出標題（新書目則整行當查詢），依序比對：</P>
        <ol className="m-0 flex list-decimal flex-col gap-1.5 pl-5 font-tc text-[15px] leading-relaxed">
          <li>有 <b>DOI</b>、doi.org 網址、<b>arXiv</b> 編號或網址：直接用 DOI 取書目，結果一定是 exact。</li>
          <li><b>IEEE Xplore 連結</b>只有文章編號、沒有 DOI，網站也擋伺服器讀取：系統拿條目本身的標題去 Crossref 找 IEEE 出版品，DOI 結尾對得上文章編號才算；對不上請改貼該頁顯示的 DOI。</li>
          <li><b>標題</b>：Crossref 與 OpenAlex 各取前幾筆，標題正規化後（忽略大小寫與標點）完全相同的就是 exact；都沒有再問 Semantic Scholar。</li>
          <li>沒有完全相同的：拿最像的一筆當 <b>fuzzy</b>，其餘列成候選；完全沒結果是 <b>none</b>。</li>
        </ol>
        <P>查過的標題與 DOI 會快取 30 天；none 不快取，修正錯字再查就是新的查詢。頁首若出現「限流」提醒，代表該來源的免費額度暫時用完，那段時間查到的結果會少一個來源，可以晚一點用「重查」再試。</P>

        <H>預覽確認：你可以做什麼</H>
        <ul className="m-0 flex list-none flex-col gap-2 p-0 font-tc text-[15px] leading-relaxed">
          <li><b>fuzzy</b> 卡片顯示「目前採用」的論文與其他候選，候選按「就是這篇」即可換掉。</li>
          <li><b>重查</b>：貼 DOI、網址或完整標題，結果列在輸入欄下方，目前採用的不會變，選了才換。</li>
          <li><b>跳過，不調整</b>：這筆完全不送 LLM，寫回時保持原文，只跟著重新編號。學位論文、網頁、資料集常查不到，確定條目沒錯就勾起來。上方有全選 / 全不選。</li>
          <li>直接按「確認無誤，繼續」：fuzzy 採用目前採用的論文，none 以原始條目的文字套格式。</li>
        </ul>

        <H>引用順序怎麼算</H>
        <P>IEEE 規則：編號依本文第一次出現的順序，清單跟著排。系統只信本文裡的 <C>[n]</C>，所以改本文的數字就是改引用對象，順序與清單會自動修正。能讀的寫法：<C>[3]</C>、<C>[3, 5]</C>、<C>[3]–[5]</C>、<C>[3-5]</C>、<C>[+1]</C>、<C>[2, +1]</C>。寫回時三個以上連號會壓成 <C>[3]–[5]</C>。</P>
        <P><b>唯一的事實是：你上傳當下清單裡已經有的那些論文，以及本文每個數字當時指到的那一篇。系統只會重排編號，數字會變，但每個引用對應到哪一篇論文絕對不變。所以要換引用對象，就改本文的數字指到你要的那篇；清單順序由系統負責。</b></P>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(440px,1fr))] gap-4">
          <Ex demo={SCENARIOS.swap} title="單純換一篇：[2] 改成 [5]，其他地方不動" before="…如 [2] 所述… → 改成 …如 [5] 所述…；舊 [2] 在後面還有引用" after="條目 5 成為新的 [2]，舊 2 依後面被引用的位置排；這個例子剛好兩者互換，沒有警告" note="若舊 [2] 在本文別處都沒再引用，它不會被刪，而是移到舊條目最後，並出現「內文沒引用到」警告。" />
          <Ex demo={SCENARIOS.exchange} title="兩處對調：[2] 改成 [5]、[5] 改成 [2]" before="…如 [2] 所述…能耗見 [5]… → …如 [5] 所述…能耗見 [2]…" after="清單裡條目 2 與 5 互換位置，其他編號不變" note="本文的數字最後會依出現順序再重寫一次，所以看起來又是 [2]、[5]，但指向的論文已經對調。" />
          <Ex warn demo={SCENARIOS.trap} title="同一篇引用了兩處，只改了一處" before="…如 [3] 所述…方法見 [3]… → 只把前面改成 …如 [5] 所述…，後面忘了改" after="舊 5 變成 [3]、舊 3 變成 [5]；後面那處顯示成 [5]，看起來像換成功了，其實仍指舊的第 3 篇" note="同一篇在本文引用了幾處就要改幾處；改之前先用 Word 搜尋「[3]」把每一處找出來。系統只認數字指到的論文，不猜你的意圖。" />
          <Ex demo={SCENARIOS.replace} title="換一篇引用：直接改數字" before="…如 [3] 所述… → 改成 …如 [15] 所述…" after="條目 15 搬到原本 3 的位置，其他條目順延；清單同步重排" note="不必動清單。原本的 [3] 若後面還有引用，就依後面的位置排；完全沒引用了，見下一條。" />
          <Ex demo={SCENARIOS.uncited} title="清單有、本文沒引用" before="清單 30 筆，本文從沒出現 [16]" after="[16] 移到舊條目最後成為 [29]，工作詳情出現「內文沒引用到」警告" note="系統不會刪條目。請決定要在本文補引用，或自己從清單刪掉。" />
          <Ex demo={SCENARIOS.unknown} title="本文引用了清單沒有的編號" before="清單 30 筆，本文出現 [54]" after="[54] 原樣保留，出現「清單裡沒有」錯誤；同一組裡的其他編號照常重編" note="例如 [3, 54] 會變成 [新的3], [54]（寫回時每個編號各自加方括號）。請手動補條目或改本文。" />
          <Ex demo={SCENARIOS.placeholder} title="新書目與 [+k] 佔位符" before="工作台第 2 行輸入新書目，本文在要引用處打 [+2]" after="[+2] 換成它的正式編號，清單在對應位置插入格式化後的條目" note="k 是左側編號（第幾篇新書目），不是行數。本文沒放 [+k] 的新書目會排在清單最後，並列進「內文沒引用到」。" />
          <Ex demo={SCENARIOS.duplicate} title="新書目其實已經在清單裡（智慧模式）" before="輸入的標題與既有 [7] 相同，本文打了 [+1]" after="不重複新增，[+1] 自動換成 [7]（或 7 重編後的新號）" note="預覽頁會標成「重複」。" />
          <Ex demo={SCENARIOS.skip} title="跳過的條目" before="某筆勾了「跳過，不調整」" after="文字保持原樣，只有編號跟著順序改" note="不送 LLM，不會有格式或審查附註。" />
        </div>

        <H>套格式、審查、寫回</H>
        <ul className="m-0 flex list-none flex-col gap-2 p-0 font-tc text-[15px] leading-relaxed">
          <li>每筆條目各開一個 LLM 工作階段，依實驗室 IEEE 規則重寫（作者縮寫、期刊縮寫、斜體刊名、en dash 頁碼等），再由第二個工作階段對照原文與查到的書目審查；審查附註以中文記在工作詳情裡。</li>
          <li>查到的書目資料（作者、年份、卷期頁）優先於原文；查不到的欄位不會被編造，而是列在附註請你補。</li>
          <li>寫回用 Word 修訂模式，修訂作者是工作台填的名字（預設 ESALab-RefBot，可在「設定」改）。本文的編號改動、清單重排與重寫，全部是可接受 / 拒絕的修訂。</li>
          <li>下載檔名：<C>原檔名_esaref_yymmdd.docx</C>；同一天同一份檔案再做一次，依序加 <C>_1</C>、<C>_2</C>。</li>
          <li>工作查完書目後可以先離開，之後從「我的紀錄」回來；伺服器重啟也會接著處理。</li>
        </ul>

        <H>期刊、會議、組織的縮寫從哪裡來</H>
        <P>實驗室規則要求刊名一律縮寫（<C>IEEE Trans. Biomed. Eng.</C>、<C>Sci. Rep.</C>、<C>Proc. CVPR</C>）。系統不維護縮寫表，縮寫由三個來源合成，優先順序如下：</P>
        <ol className="m-0 flex list-decimal flex-col gap-1.5 pl-5 font-tc text-[15px] leading-relaxed">
          <li><b>Crossref 的 short-container-title</b>：出版社登錄 DOI 時附的官方縮寫，查到時會以 <C>venue_short</C> 一起交給 LLM，這是最可靠的來源。OpenAlex 與 Semantic Scholar 只有全名，沒有這個欄位。</li>
          <li><b>規則檔的範例與規則</b>：IEEE 期刊用 IEEE 縮寫表，其他期刊用 ISO 4 / LTWA（<C>Journal</C>→<C>J.</C>、<C>International</C>→<C>Int.</C>、去掉 and / of / the），單字刊名不縮；會議去掉 <C>Proceedings of the</C> 改成 <C>Proc.</C>，知名縮寫（CVPR、ICRA、NeurIPS）可單獨使用。</li>
          <li><b>LLM 自己的知識</b>：沒有官方縮寫時由模型依上述規則推，不確定可以上網查 ISO 4 / IEEE 縮寫表（只開放 webfetch，不能改檔或執行指令）。</li>
        </ol>
        <P>組織名稱（IEEE、ACM、IET、Elsevier、Univ.）只有既有條目或書目資料裡寫了才會出現，系統不會憑空補上出版社。縮寫是審查階段會特別檢查的項目之一：審查 LLM 比對原文與書目資料，拿不準的會寫進附註，請在工作詳情裡看一下。拿到的縮寫若與實驗室慣例不同，直接在 Word 修訂裡拒絕該筆即可。</P>

        <H>用 AI 客戶端操作</H>
        <P>Claude Code、Cursor 等支援 MCP 的客戶端可以接進來，上傳用 curl，其餘動作都是工具。設定方式與工具清單在 <a href="#/mcp">MCP</a> 頁。</P>

        <H>單筆查詢</H>
        <P>貼標題、DOI 或網址，先只查資料庫（幾秒），確定是這篇再按「產生」跑 LLM 套格式與審查，結果可以複製成保留斜體的 Word 格式。產生紀錄與附註都會留在這一頁，點開即可展開。</P>
      </div>
    </Shell>
  )
}
