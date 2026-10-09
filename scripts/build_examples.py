"""Rebuild translated saved narratives without modifying evidence or exact quotations.

This is an offline publishing utility, never a search or fact-verification operation.
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TRANSLATIONS = {
    "en": {
        "topic": "Humans landed on the Moon successfully only once, with no later crewed landings.",
        "scope": "Saved demonstration, manually compiled after opening NASA pages during development; loading it does not search again. Scope: crewed Apollo lunar surface landings in 1969–1972 only. No claim is made about missions after 1972 or the all-history total as of 2026. A successful landing here means a crewed lunar module landed on the Moon and the mission returned to Earth. First/subsequent landings, orbit/flyby, robotic missions, and Earth splashdown are distinct. Timeline dates are lunar landing dates, except Apollo 13 uses its launch date and explicitly notes the later cancellation. Apollo 16 uses the dedicated source's 1972-04-21 UT date.",
        "limitations": [
            "This is a fixed example checked online during development, not live research for the current input. Pages can change and should be reopened for a new investigation.",
            "All five sources are NASA materials in the NASA-Apollo family. Internal cross-checks do not constitute confirmation by five independent institutions.",
            "The example checks mission counts and types. It does not independently reanalyse telemetry, samples, or all communications, and does not infer other disputed claims.",
            "The NSSDCA overview gives April 20 for Apollo 16, while the dedicated page gives April 21 UT and April 20 locally in the US. The timeline uses the explicit UT date; the annual count is unaffected.",
            "The newer NASA overview describes Apollo 14 walks under January 1971. The NSSDCA list distinguishes the January 31 launch from the February 5 landing. This example uses the latter landing date.",
            "Evidence excerpts are faithful Chinese paraphrases, not verbatim quotations; they remain unchanged in this translated narrative. Context identifies the original passage. The source text was opened, not merely inferred from search snippets.",
            "E1 has an actual full-page browser capture of the original NASA page, preserved with SHA-256. The other sources have no captures. An image aids review and does not independently prove a historical event.",
            "search_log lists two key exact searches for verification, not the complete browsing history. Result counts are returned entries, not independent sources.",
            "Annual counts deterministically count listed missions; exact entries and inclusion rules accompany points. Validation does not establish list completeness. The 1970 zero means no successful landing entry in this list."
        ],
        "claims": [
            ["During Apollo in 1969–1972, humans completed only one successful crewed lunar surface landing.", "Inconsistent with the listed records for this period", "NSSDCA lists six landing-and-return missions: Apollo 11, 12, 14, 15, 16, and 17. NASA's visualization and overview also list six landings. This compares the same period and mission type."],
            ["After Apollo 11's first landing, no further successful crewed lunar surface landing occurred through the end of 1972.", "Five later mission records run counter to this claim", "Apollo 12, 14, 15, 16, and 17 landed after Apollo 11. One qualifying later example tests a universal 'never again' claim; the list supplies five."],
            ["Apollo 13 cancelled its planned lunar landing in 1970 and cannot count as a successful lunar surface landing.", "Supported by the official mission record", "NASA says the planned third landing was cancelled after an oxygen-tank accident and the crew returned safely. 'Successful failure' describes the rescue, not a completed lunar landing."]
        ],
        "contexts": [
            "Faithful Chinese paraphrase retained. See the opening paragraph and Apollo Lunar Missions list, last updated 2023-02-17. The page separates Apollo 8/10 orbit from landings. Apollo 16's explicitly timed UT date is cross-checked with E4 rather than assuming a timezone for April 20.",
            "Faithful Chinese paraphrase retained. See the first two paragraphs: period, six sites, and the Apollo 13 exception. Article date 2019-11-14; updated 2025-02-12. The text was read, not the video frame by frame. Its NASA sources are not independent of E1's institution.",
            "Faithful Chinese paraphrase retained. See Mission Objective and early Mission Highlights. The 'successful failure' rescue is distinct from the cancelled landing. The later Landing field concerns return to Earth.",
            "Faithful Chinese paraphrase retained. See the mission-date fields below the title; updated 2022-08-15. Use the stated UT time without silently correcting the parenthetical timezone abbreviation. Day-level differences do not change the 1972 count.",
            "Faithful Chinese paraphrase retained. See the Lunar Landing Missions count, Apollo 11/12 sections, and Apollo Lunar Surface Journal description. The Apollo 14 month discrepancy prevents using that overview for the precise landing date. Official identity is not sufficient to accept every detail."
        ],
        "link_notes": ["Six missions in the same list meet this report's definition; this relationship is an analytical annotation.", "Six sites in 1969–1972 cross-check the count within the same institution as E1.", "The overview cross-checks six landings; precise dates come from mission entries.", "The list records Apollo 12, 14, 15, 16, and 17 after Apollo 11.", "Apollo 16 is a specific later landing with an explicit UT date.", "Mission objectives and highlights explicitly state cancellation.", "The list identifies Apollo 13 as a flyby and return with its landing cancelled.", "A cancelled landing is excluded from successful counts and does not determine later outcomes."],
        "timeline": [
            ["Apollo 11: lunar landing", "Landed in the Sea of Tranquility, first of six listed successful crewed landings in this period. Earth splashdown is a different date."],
            ["Apollo 12: lunar landing", "Landed in the Ocean of Storms after Apollo 11; NASA's overview describes it as the second lunar landing."],
            ["Apollo 13: launch; landing later cancelled", "This is the launch date, not a landing date. The April 11–17 mission suffered a failure, cancelled its landing, flew by the Moon, and returned safely. It is excluded from successful landings."],
            ["Apollo 14: lunar landing", "Landed at Fra Mauro. NSSDCA distinguishes the January 31 launch and February 5 landing; the dates cannot be interchanged."],
            ["Apollo 15: lunar landing", "Landed in the Hadley Rille region and is counted in 1971."],
            ["Apollo 16: lunar landing (UT date)", "Landed at Descartes. The dedicated record states April 21 at 02:23:35 UT and April 20 locally in the US. The timeline uses the explicit UT date."],
            ["Apollo 17: lunar landing", "Landed at Taurus-Littrow, the sixth listed successful crewed landing within this Apollo period. No later period is assessed here."]
        ],
        "chart": ["Successful crewed Apollo lunar landings, 1969–1972", "missions", "Count of E1's listed successful missions by lunar landing year: Apollo 11/12 in 1969, 14/15 in 1971, 16/17 in 1972; 2+0+2+2=6. Apollo 13's cancelled 1970 landing counts as zero successful landings. The unit is missions, not people, launches, orbits, or robotic landings. This is a report-derived chart, not a NASA figure."],
        "calculation": "Count E1's listed successful crewed lunar landing-and-return mission entries by landing year. Unit: missions; only the cited list is counted, and its completeness requires separate review.",
        "comparisons": [
            ["Later comparable mission: Apollo 12 and Apollo 11", "Both are Apollo crewed lunar landing-and-return missions under the same counting definition.", "Apollo 11 was first and landed in the Sea of Tranquility; Apollo 12 was later and landed in the Ocean of Storms.", "A direct comparison of records in one period distinguishes first from only once. It does not use resemblance to prove authenticity or infer counts in other periods."],
            ["Different outcomes: Apollo 13 and completed landings", "All were crewed Apollo flights; Apollo 13 also planned to land.", "Apollo 13 cancelled the landing and returned safely, while Apollo 11, 12, 14, 15, 16, and 17 completed lunar landings. Rescue and completion of the original surface mission are different outcomes.", "Apollo 13's outcome concerns that mission only. A single failure does not establish failure of earlier/later missions, and 'successful failure' is not a successful lunar landing."]
        ],
        "observations": [
            "Deduplicating E1's landing-and-return entries and counting missions by landing year gives 2 (11/12) in 1969, 0 in 1970, 2 (14/15) in 1971, and 2 (16/17) in 1972: six total. The 1970 zero refers to listed successful landings, not an absence of crewed flights; E3 records Apollo 13. Launches, people, orbits, and robotic missions are separate units.",
            "E5 describes Apollo 11 as first and Apollo 12 as second. 'First' specifies order; 'only once' specifies a count in a defined scope. Checking these phrases requires an ordering reference, a counting period, and an event definition. Order and total count are different checks.",
            "Apollo 13 and 14 belonged to the same program. E3 says Fra Mauro was planned for Apollo 13 and reassigned to Apollo 14 after cancellation; E1 records Apollo 14's February 5, 1971 landing. Plans and sites are comparable, while execution differed. This comparison does not cover unresearched later periods or other programs.",
            "E1 gives April 20 for Apollo 16 without a timezone; E4 gives April 21 at 02:23:35 UT and April 20 locally in the US. Day-level timelines should state the time standard. Both dates fall in 1972, leaving the annual count unchanged."
        ],
        "reasoning": [
            "Deduplicate NASA's listed missions under the same crewed lunar landing-and-return definition: 11, 12, 14, 15, 16, 17. Annual counts 2, 0, 2, 2 sum to six. This computes records; it does not vote by website count.",
            "'No success after the first' is universal. Five recorded later landings, including Apollo 12, are specific contrary cases. Direct mission records are available; historical analogy need not substitute for them.",
            "NASA separately describes Apollo 13's cancelled landing and rescued crew. Under the surface-landing definition it is excluded; that failure does not erase other recorded successes.",
            "Apollo 16's dedicated source gives April 21 UT and April 20 locally. Selecting UT resolves the day-level display, while both the annual and total counts remain unchanged."
        ],
        "questions": ["Does 'Moon landing' mean a crewed surface landing, a lunar orbit, a robotic landing, or a launch toward the Moon? These units cannot be mixed.", "Investigating 1972 to the present needs a separate study with a cutoff date, not extrapolation from this example.", "Should non-NASA original observations, sample research, or independent archives be added to assess source independence?", "For exact landing times, use timezone-labelled records and distinguish lunar landing from Earth splashdown."],
        "summary": ["Within Apollo in 1969–1972, NASA records list six successful crewed lunar surface landings: Apollo 11, 12, 14, 15, 16, and 17. Apollo 11's 'first' does not mean 'only'; five followed. Apollo 13's landing was cancelled and is excluded. This finding covers that period only and makes no judgment about later mission totals. This saved demonstration judgment belongs only in AI-summary mode.", "Within the stated Apollo period, the claim conflicts with the listed records", ["NASA sources share one institutional provenance; internal cross-checks are not independent-institution verification.", "This example was saved after development-time online checks, not generated by this click's live search.", "Day-level dates require timezones; Apollo 16 uses April 21 UT from its dedicated page.", "The conclusion concerns only stated mission counts/types, not other disputes or present all-history totals."]],
        "search_intents": ["NASA-domain exact verification of six listed successes; four results were returned, with duplicate documents not counted independently.", "NASA-domain verification of Apollo 16's date/timezone; nine results returned, but only the opened dedicated NSSDCA page was used, not unrelated parameterized pages."]
    },
    "ja": {
        "topic": "人類が有人月面着陸に成功したのは一度だけで、その後の有人着陸はない。",
        "scope": "開発時に NASA の原ページを開いて確認し、手動で構成した保存例です。読み込みで新規検索は行いません。対象は 1969～1972 年のアポロ計画における有人月面着陸のみで、1972 年以降や 2026 年現在の全歴史の総数は判断しません。成功とは有人着陸船が月面に着陸し、地球への帰還を完了した任務です。初回・後続着陸、周回・飛行通過、無人探査、地球への着水は区別します。年表は月面着陸日を用い、Apollo 13 のみ打上げ日と着陸中止を明記します。Apollo 16 は専用資料の 1972-04-21 UT を使用します。",
        "limitations": [
            "開発時にオンライン確認した固定例で、現在の入力についてのリアルタイム調査ではありません。ページは変更され得るため、新規調査では再確認してください。",
            "五つの出典はすべて NASA-Apollo 系統の NASA 資料です。同一機関内の照合であり、五つの独立機関による確認ではありません。",
            "任務の回数と種類を検証しています。遠隔測定、試料、全通信記録を独立に再解析しておらず、他の論争へ推論を広げません。",
            "Apollo 16 は総覧で 4 月 20 日、専用ページで 4 月 21 日 UT・米国現地 4 月 20 日と記載されています。年表は明示された UT 日付を使用し、年間回数は影響を受けません。",
            "新版総覧は Apollo 14 の月面歩行を January 1971 と概述しますが、NSSDCA は 1 月 31 日の打上げと 2 月 5 日の着陸を区別します。本例は後者を使います。",
            "excerpt は中国語の忠実な要約で、逐語引用ではありません。翻訳版でも原資料欄を保持し、context で該当箇所を示します。検索要約だけでなく本文を開いて確認しました。",
            "E1 は NASA 原ページを実際のブラウザーで撮影した全体画像と SHA-256 を含みます。他の出典は未撮影です。画像は位置確認用で、歴史的事実の独立した証明ではありません。",
            "search_log は重要な二件の厳密検索で、全閲覧履歴ではありません。結果数は返された項目数で、独立出典数ではありません。",
            "年間回数は列挙された任務の確定的な件数です。引用項目・条件を示しますが、検証処理は一覧の完全性を証明しません。1970 年のゼロは成功着陸項目がないことです。"
        ],
        "claims": [
            ["1969～1972 年のアポロ計画で、人類の有人月面着陸成功は一回だけだった。", "この期間の列挙記録と一致しない", "NSSDCA は着陸・帰還を完了した Apollo 11、12、14、15、16、17 の六任務を列挙します。NASA の可視化と総覧も六回を示します。同期間・同種類で比較しています。"],
            ["Apollo 11 の初着陸後、1972 年末まで有人月面着陸の成功はなかった。", "五つの後続記録が反対の事例を示す", "Apollo 12、14、15、16、17 は Apollo 11 より後に着陸しました。「その後一度もない」という全称主張には一件の該当例でも検証材料となり、一覧には五件あります。"],
            ["Apollo 13 は 1970 年の予定着陸を中止したため、成功した有人月面着陸に数えられない。", "公式任務記録に支持される", "NASA は酸素タンク事故による第三回予定着陸の中止と乗員の安全帰還を記録します。successful failure は救助を述べる表現で、月面着陸完了ではありません。"]
        ],
        "contexts": [
            "中国語の忠実な要約を保持。冒頭と Apollo Lunar Missions 一覧を参照。最終更新 2023-02-17。Apollo 8・10 の周回と着陸を区別します。Apollo 16 の時区不明な 4 月 20 日はそのまま使わず、E4 の UT 表記と照合しました。",
            "中国語の忠実な要約を保持。最初の二段落が期間・六地点・Apollo 13 の例外を示します。記事 2019-11-14、更新 2025-02-12。本文を確認し、動画全フレームを検証したとは主張しません。参照資料も NASA 系で E1 から機関的に独立していません。",
            "中国語の忠実な要約を保持。Mission Objective と Mission Highlights 冒頭を参照。救助成功と着陸中止を区別します。後部の Landing 欄は地球帰還を示します。",
            "中国語の忠実な要約を保持。タイトル直下の任務日付欄。更新 2022-08-15。明示された UT を使い、括弧内時区略称を黙って修正しません。日付差は 1972 年の回数を変えません。",
            "中国語の忠実な要約を保持。Lunar Landing Missions 数値、Apollo 11・12 節、Surface Journal 説明を参照。Apollo 14 の月に相違があるため正確な日付には用いません。公式であることだけで全細部を採用しません。"
        ],
        "link_notes": ["同定義に該当する六任務を一覧が示します。関係表示は分析上の注釈です。", "1969～1972 年の六地点で回数を照合しますが、E1 と同一機関です。", "総覧の六回と照合し、正確な日付は任務一覧を使用します。", "Apollo 11 後の 12、14、15、16、17 を列挙します。", "Apollo 16 は初回以降の具体例で UT 日付を示します。", "目標と経過に着陸中止を明記します。", "一覧は Apollo 13 の飛行通過・帰還と着陸中止を示します。", "中止した任務は成功回数に含めず、後続任務全体を代表しません。"],
        "timeline": [
            ["Apollo 11：月面着陸", "静かの海に着陸。この期間の成功六任務の初回です。地球への着水日は別に扱います。"],
            ["Apollo 12：月面着陸", "Apollo 11 後に嵐の大洋へ着陸し、NASA 総覧は第二回と説明します。"],
            ["Apollo 13：打上げ、のちに着陸中止", "この日付は打上げ日です。4 月 11～17 日の任務中に故障し、着陸を中止して月を通過、安全帰還しました。成功着陸には含めません。"],
            ["Apollo 14：月面着陸", "Fra Mauro に着陸。NSSDCA は 1 月 31 日の打上げと 2 月 5 日の着陸を区別し、混同できません。"],
            ["Apollo 15：月面着陸", "Hadley Rille 地域に着陸。1971 年に計上します。"],
            ["Apollo 16：月面着陸（UT 日付）", "Descartes に着陸。専用記録は 4 月 21 日 UT 02:23:35 と米国現地 4 月 20 日を示します。明示された UT 日付を使用します。"],
            ["Apollo 17：月面着陸", "Taurus-Littrow に着陸。この期間における六回目の成功で、以降の年代は判断しません。"]
        ],
        "chart": ["1969～1972 年のアポロ有人月面着陸成功回数", "任務", "E1 の成功一覧を着陸年で数えます。1969 年は 11・12、1971 年は 14・15、1972 年は 16・17、2+0+2+2=6。1970 年の Apollo 13 は中止で成功ゼロです。人数・打上げ・周回・無人着陸は含めません。本レポートの集計図で、NASA 原図ではありません。"],
        "calculation": "E1 の有人月面着陸・帰還成功一覧から、月面着陸年で該当任務を数えます。単位は任務。引用一覧内のみの集計で、完全性は別途確認が必要です。",
        "comparisons": [
            ["同種の後続任務：Apollo 12 と Apollo 11", "どちらも同じ定義のアポロ有人月面着陸・帰還任務です。", "Apollo 11 は初回で静かの海、Apollo 12 は後続で嵐の大洋に着陸しました。", "同期間の記録を直接比較し、「初回」と「一度だけ」を区別します。外観や類似から真偽を推論せず、他の年代の回数に広げません。"],
            ["結果の違い：Apollo 13 と成功した着陸", "すべて有人アポロ飛行で、Apollo 13 にも着陸計画がありました。", "Apollo 13 は着陸中止・安全帰還、11・12・14・15・16・17 は月面着陸完了です。救助と原予定の月面任務完了は別の結果です。", "Apollo 13 の結果はその任務だけです。一度の失敗から前後すべての失敗を導けず、successful failure を登月成功と解釈できません。"]
        ],
        "observations": [
            "E1 の着陸・帰還項目を重複排除し、任務を着陸年で数えると、1969 年 2（11・12）、1970 年 0、1971 年 2（14・15）、1972 年 2（16・17）、計 6 です。ゼロは成功一覧の該当なしで、有人飛行なしではありません。E3 に Apollo 13 を記録。人数、打上げ、周回、無人任務を混ぜません。",
            "E5 は Apollo 11 を初回、12 を第二回と述べます。「初回」は順序、「一度だけ」は一定範囲の総数を限定します。照合には順序の参照範囲、集計期間、事象の定義が必要で、順序と総数は別項目です。",
            "Apollo 13・14 は同計画です。E3 は 13 に予定された Fra Mauro が中止後 14 に移されたと説明し、E1 は 1971 年 2 月 5 日の着陸を記録します。計画と場所は類似しますが実行結果は異なります。未調査の他年代・他計画は比較範囲外です。",
            "Apollo 16 は E1 に時区なしの 4 月 20 日、E4 に UT 4 月 21 日 02:23:35 と米国現地 4 月 20 日があります。日単位では時刻基準を明示します。どちらも 1972 年なので年集計は変わりません。"
        ],
        "reasoning": [
            "同じ有人月面着陸・帰還定義で NASA の任務を重複排除すると 11・12・14・15・16・17 の六件です。年間 2・0・2・2、計 6。資料の計算であり、サイト数の投票ではありません。",
            "「初回後の成功なし」は全称主張です。Apollo 12 など五件は具体的な反対事例です。直接の任務資料を歴史的類推で置き換える必要はありません。",
            "NASA は Apollo 13 の着陸中止と乗員救助を区別します。着陸定義では成功に含めず、その失敗は他の成功記録を消しません。",
            "Apollo 16 専用資料は UT 4 月 21 日と現地 4 月 20 日を併記します。UT を採用して日表示を整合させても、年回数と総数は不変です。"
        ],
        "questions": ["登月とは有人着陸、周回、無人着陸、月への打上げのどれですか。単位を混ぜて数えられません。", "1972 年以降から現在までは締切日を定めた別調査が必要で、本例から外挿できません。", "情報源の独立性を調べるため、NASA 以外の原観測、試料研究、独立資料を追加しますか。", "正確な着陸時刻は時区付き記録を使い、月面着陸と地球への着水を区別してください。"],
        "summary": ["1969～1972 年のアポロ計画に限定すると、NASA は Apollo 11・12・14・15・16・17 の有人月面着陸成功六回を記録します。初回の 11 は唯一ではなく、五回が続きました。13 は着陸中止のため含めません。以降の任務総数は判断しません。この保存例の判断は AI 要約モードのみで表示します。", "限定したアポロ期間で、この主張は列挙記録と一致しない", ["出典は NASA の同一系統で、独立機関による検証ではありません。", "開発時に確認した保存例で、今回の操作によるリアルタイム検索ではありません。", "日付は時区に注意し、Apollo 16 は専用ページの UT 4 月 21 日を使います。", "結論は指定範囲の回数・種類のみで、他の論争や現在の全歴史総数へ広げません。"]],
        "search_intents": ["NASA ドメイン内の厳密検索で六成功任務を照合。結果四件の重複資料は独立出典に数えません。", "NASA 内で Apollo 16 の日付・時区を照合。結果九件のうち実際に開いた NSSDCA 専用ページのみを採用しました。"]
    }
}


def build():
    base_path = ROOT / "examples/demo-report.json"
    original = json.loads(base_path.read_text(encoding="utf-8"))
    original.update(language="zh-CN", summary_language="zh-CN", source_policy="balanced", preferred_sources=[])
    base_path.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for language, words in TRANSLATIONS.items():
        report = copy.deepcopy(original)
        report.update(language=language, summary_language=language, topic=words["topic"], scope=words["scope"], limitations=words["limitations"], questions=words["questions"])
        for item, texts in zip(report["claims"], words["claims"]): item.update(zip(("text", "verdict", "analysis"), texts))
        for item, text in zip(report["evidence"], words["contexts"]): item["context"] = text
        for item, text in zip(report["links"], words["link_notes"]): item["note"] = text
        for item, texts in zip(report["timeline"], words["timeline"]): item.update(zip(("title", "detail"), texts))
        for item in report["charts"]:
            item.update(zip(("title", "unit", "note"), words["chart"]))
            for point in item["points"]: point["calculation"]["description"] = words["calculation"]
        for item, texts in zip(report["comparisons"], words["comparisons"]): item.update(zip(("case", "similarities", "differences", "limits"), texts))
        for item, text in zip(report["observations"], words["observations"]): item["text"] = text
        for item, text in zip(report["reasoning"], words["reasoning"]): item["text"] = text
        report["summary"].update(zip(("text", "verdict", "caveats"), words["summary"]))
        for item, text in zip(report["search_log"], words["search_intents"]): item["intent"] = text
        (ROOT / f"examples/demo-report.{language}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
    print("Saved examples rebuilt / 已重建保存示例 / 保存例を再構築しました")
