"""Localize application messages; never translate source excerpts or citations."""
from __future__ import annotations

import re


SUPPORTED_LANGUAGES = ["zh-CN", "en", "ja"]


def tr(zh: str, en: str, ja: str, language: str = "zh-CN") -> str:
    return en if language == "en" else ja if language == "ja" else zh


ERRORS = {
    "local_only": ("This service only accepts requests from this computer.", "このサービスは、このコンピューターからのアクセスのみを受け付けます。"),
    "origin_blocked": ("Cross-site request blocked.", "クロスサイトリクエストをブロックしました。"),
    "body_too_large": ("The request body exceeds the 1 MB limit.", "リクエスト本文が上限の 1 MB を超えています。"),
    "invalid_request": ("Invalid request fields. Check the topic, mode, language, AI settings, and report format.", "入力形式が正しくありません。テーマ、モード、言語、AI 設定、レポート形式を確認してください。"),
    "internal_error": ("Processing failed. Check the configuration and try again. No substitute result was generated.", "処理に失敗しました。設定を確認して再試行してください。代替結果は生成していません。"),
    "not_found": ("The requested resource does not exist.", "指定されたリソースは存在しません。"),
    "unsafe_url": ("Address blocked: only public HTTP/HTTPS targets and safe ports are allowed. AI endpoints may use explicit local loopback addresses.", "アドレスをブロックしました。公開 HTTP/HTTPS と安全なポートのみ利用できます。AI 接続先には明示的なローカルループバックアドレスも利用できます。"),
    "dns_failed": ("The source address could not be resolved.", "情報源のアドレスを名前解決できませんでした。"),
    "redirect_blocked": ("The target returned a disallowed redirect or exceeded the redirect limit.", "許可されていないリダイレクト、またはリダイレクト回数の上限を検出しました。"),
    "content_too_large": ("The source exceeds the safe content-reading limit.", "情報源の内容が安全な読み取り上限を超えています。"),
    "network_error": ("The connection failed or timed out. Check the network and service address.", "接続に失敗したか、タイムアウトしました。ネットワークとサービスのアドレスを確認してください。"),
    "invalid_model_output": ("The AI response does not satisfy the required JSON report or evidence requirements. Try again or use a compatible model; no substitute report was generated.", "AI の応答が必要な JSON 形式、レポート構造、または証拠要件を満たしていません。再試行するか対応モデルを選んでください。代替レポートは生成していません。"),
    "missing_ai_model": ("Enter an AI model name or set TRUTH_AI_MODEL.", "AI モデル名を入力するか、TRUTH_AI_MODEL を設定してください。"),
    "missing_ai_key": ("Enter an AI API key or set TRUTH_AI_API_KEY. Local compatible services may leave it blank.", "AI API キーを入力するか、TRUTH_AI_API_KEY を設定してください。ローカルの互換サービスでは空欄にできます。"),
    "invalid_search_output": ("The search provider returned an invalid response format.", "検索プロバイダーの応答形式が正しくありません。"),
    "unsupported_content": ("This version extracts HTML and plain text only. Review PDF, audio, or video sources manually.", "このバージョンは HTML とプレーンテキストのみ抽出します。PDF、音声、動画は手動で確認してください。"),
    "empty_text": ("Fewer than 80 text characters were retrieved. The page may require scripts, login, or manual access.", "取得できた本文が 80 文字未満です。スクリプト、ログイン、または手動アクセスが必要な可能性があります。"),
    "invalid_evidence_reference": ("Evidence validation failed: check source IDs, claim IDs, exact quotations, chart numbers, derived counts, and reasoning order. No substitute report was generated.", "証拠の検証に失敗しました。情報源 ID、主張 ID、原文引用、グラフ数値、派生件数、推論順序を確認してください。代替レポートは生成していません。"),
    "no_search_results": ("Search returned no usable sources. Narrow the topic or change the queries.", "検索で利用可能な情報源が見つかりませんでした。テーマを絞るか、検索語を変更してください。"),
    "no_safe_sources": ("None of the search sources could be accessed safely. No report was generated.", "検索結果に安全にアクセスできる情報源がありませんでした。レポートは生成していません。"),
    "no_evidence": ("There is no evidence to summarize. Search first or import a report containing sources.", "要約に使える証拠がありません。先に検索するか、情報源を含むレポートを読み込んでください。"),
    "demo_unavailable": ("The demo report for this language is missing or invalid. No translated substitute is used.", "この言語のデモレポートがないか、形式が正しくありません。翻訳による代替は行いません。"),
    "invalid_source_credentials": ("Invalid source credentials. Use one exact public HTTPS origin per account, Basic username/password or a Cookie/Bearer token, with no control characters. Nothing is stored.", "情報源の認証情報が無効です。公開 HTTPS の正確な origin ごとに 1 件を指定し、Basic のユーザー名・パスワード、または Cookie/Bearer トークンを使用してください。制御文字は使用できません。認証情報は保存しません。"),
    "invalid_source_scope": ("The preferred source scope is missing or exceeds the search provider's query limit. Specify up to six public source URLs with shorter domains.", "優先情報源の範囲がないか、検索プロバイダーの上限を超えています。短いドメインの公開 URL を最大 6 件指定してください。"),
    "credentials_in_public_input": ("The topic or a preferred URL/label contains submitted account credentials. Remove them and provide credentials only through the source-account fields.", "テーマまたは指定 URL・ラベルに、提出した認証情報が含まれています。削除し、認証情報は情報源のアカウント欄のみに入力してください。"),
}


def error_message(code: str, original: str, language: str = "zh-CN") -> str:
    if language == "zh-CN":
        return original
    if code == "missing_search_key":
        provider = "Tavily" if "Tavily" in original else "Brave" if "Brave" in original else "search provider"
        return tr(original, f"Enter a {provider} search API key. Live research requires a real search service and never substitutes demo data.",
                  f"{provider} の検索 API キーを入力してください。実際の検索サービスが必要です。デモデータによる代替は行いません。", language)
    if code in {"provider_error", "source_http_error"}:
        status_match = re.search(r"HTTP (\d{3})", original)
        status = status_match.group(1) if status_match else "unknown"
        provider = "Tavily" if "Tavily" in original else "Brave" if "Brave" in original else tr("", "AI provider" if code == "provider_error" else "Source", "AI プロバイダー" if code == "provider_error" else "情報源", language)
        details = {
            "400": ("Check the model name, compatible endpoint, and parameters.", "モデル名、互換エンドポイント、パラメーターを確認してください。"),
            "401": ("Authentication failed. Check the API key.", "認証に失敗しました。API キーを確認してください。"),
            "403": ("Permission denied or the service is unavailable.", "権限がないか、サービスを利用できません。"),
            "404": ("Endpoint or model not found. Check the base URL and model name.", "エンドポイントまたはモデルが見つかりません。Base URL とモデル名を確認してください。"),
            "429": ("Rate limit or quota exceeded.", "レート制限または利用枠を超えています。"),
        }.get(status, ("The request failed. Try again later.", "リクエストに失敗しました。しばらくしてから再試行してください。"))
        return f"{provider}: HTTP {status}. " + details[0 if language == "en" else 1]
    if code == "research_timeout":
        match = re.search(r"\d+", original)
        seconds = match.group() if match else "180"
        return tr(original, f"Processing exceeded {seconds} seconds. No incomplete or substitute report was returned; try again later.", f"処理が {seconds} 秒を超えました。不完全なレポートや代替レポートは返していません。後で再試行してください。", language)
    pair = ERRORS.get(code)
    if pair:
        return pair[0 if language == "en" else 1]
    return tr(original, "Processing failed; no substitute result was generated.", "処理に失敗しました。代替結果は生成していません。", language)


def narrative_instruction(language: str) -> str:
    return tr(
        "输出语言要求：所有新生成的说明、论断拆分、观察、比较、局限与可选判断使用简体中文。来源原文 excerpt、source_quote、calculation.source_quotes、来源 title 与 URL 必须保持原语言和原文，不得伪造翻译。外文原句可另作明确标记的解释，但精确引用不可翻译。",
        "OUTPUT LANGUAGE: Write every newly generated claim, observation, comparison, limitation, and optional judgment in English. Keep source excerpts, source_quote, calculation.source_quotes, original source titles, and URLs in their original language and wording. Never present a translation as an exact source quotation. Existing evidence and prior analysis must not be silently translated or replaced.",
        "出力言語：新たに生成する主張の分解、観察、比較、制約、任意の判断はすべて日本語で記述してください。情報源の excerpt、source_quote、calculation.source_quotes、元のタイトル、URL は元の言語・原文のまま保持してください。翻訳を正確な原文引用として提示しないでください。既存の証拠や分析を黙って翻訳・置換してはいけません。",
        language,
    )
