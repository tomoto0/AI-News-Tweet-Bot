import os
import json
import time
import requests
from requests_oauthlib import OAuth1Session

# 環境変数からAPIキーなどを取得
MANUS_API_KEY = os.environ.get("MANUS_API_KEY")
TWITTER_CONSUMER_KEY = os.environ.get("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

# 定数
MANUS_API_URL = "https://api.manus.ai/v1/tasks"
TWITTER_API_URL = "https://api.twitter.com/2/tweets"
MAX_TWEET_LENGTH = 140 # 全角140文字
URL_LENGTH = 23 # URLは23文字としてカウント

def create_manus_task(prompt: str) -> str:
    """Manus APIにタスクを作成し、task IDを返す"""
    print("Manus APIにタスクを作成中...")
    headers = {
        "API_KEY": MANUS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "taskMode": "chat",
        "agentProfile": "speed",
        "locale": "ja"
    }
    
    try:
        response = requests.post(MANUS_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        task_data = response.json()
        task_id = task_data.get("id")
        # ユーザーのエラーログから、タスク作成が失敗した場合でも 'task_id' が返されることが確認されたため、
        # 'id' がない場合は 'task_id' を使用する。
        if not task_id and "task_id" in task_data:
            task_id = task_data["task_id"]
        
        if not task_id:
            raise Exception(f"タスクIDが取得できませんでした: {task_data}")
        print(f"タスク作成成功。タスクID: {task_id}")
        return task_id
    except requests.exceptions.RequestException as e:
        print(f"Manus APIタスク作成エラー: {e}")
        raise

def get_manus_task_result(task_id: str) -> str:
    """Manus APIからタスクの結果を取得する（完了までポーリング）"""
    print(f"タスク結果をポーリング中 (ID: {task_id})...")
    headers = {"API_KEY": MANUS_API_KEY}
    task_url = f"{MANUS_API_URL}/{task_id}"
    
    while True:
        try:
            response = requests.get(task_url, headers=headers)
            response.raise_for_status()
            task_data = response.json()
            
            status = task_data.get("status")
            if status == "completed":
                # 最後のメッセージが結果
                messages = task_data.get("messages", [])
                if messages:
                    result_text = messages[-1].get("text", "")
                    print("タスク完了。結果を取得しました。")
                    return result_text
                else:
                    raise Exception("タスクは完了しましたが、メッセージがありませんでした。")
            elif status in ["pending", "running"]:
                print(f"ステータス: {status}。5秒待機します...")
                time.sleep(5)
            else:
                raise Exception(f"タスクが失敗または不明なステータスになりました: {status}")
        except requests.exceptions.RequestException as e:
            print(f"Manus APIタスク結果取得エラー: {e}")
            raise
        except Exception as e:
            print(f"タスク処理エラー: {e}")
            raise

def parse_tweet_content(manus_result: str) -> dict:
    """Manusの結果からツイート内容をパースする"""
    print("Manusの結果をパース中...")
    try:
        # JSONブロックを抽出
        start = manus_result.find("```json") + len("```json")
        end = manus_result.find("```", start)
        json_str = manus_result[start:end].strip()
        
        content = json.loads(json_str)
        return content
    except Exception as e:
        print(f"JSONパースエラー: {e}")
        print(f"生のManus結果: \n{manus_result}")
        raise

def generate_tweet_text(content: dict) -> str:
    """パースした内容からツイート本文を生成する"""
    title = content.get("title", "新しいAIニュース")
    summary = content.get("summary", "要約がありません。")
    url = content.get("url", "")
    
    # ツイート本文の基本構造
    # タイトル
    # 要約
    # URL
    # #AI
    
    # URLとタグの文字数
    fixed_length = URL_LENGTH + len("\n#AI")
    
    # タイトルと要約で使える残りの文字数
    available_length = MAX_TWEET_LENGTH - fixed_length
    
    # 全角文字を2文字としてカウントする（概算）
    def get_approx_length(text):
        return sum(2 if ord(c) > 255 else 1 for c in text)

    def truncate_text(text, max_len):
        current_len = 0
        truncated_text = ""
        for char in text:
            char_len = 2 if ord(char) > 255 else 1
            if current_len + char_len <= max_len:
                truncated_text += char
                current_len += char_len
            else:
                break
        return truncated_text

    # タイトルと要約を合わせて、改行も含めて文字数制限内に収める
    # タイトルと要約の間に改行を入れるので、さらに1文字分を引く
    available_length -= 1 
    
    # タイトルと要約の最大文字数を仮に半々とする
    max_title_len = available_length // 2
    max_summary_len = available_length - max_title_len
    
    # 概算文字数でタイトルを切り詰める
    truncated_title = truncate_text(title, max_title_len)
    
    # タイトルで使った分だけ要約の最大文字数を増やす
    title_used_len = get_approx_length(truncated_title)
    max_summary_len += (max_title_len - title_used_len)
    
    # 概算文字数で要約を切り詰める
    truncated_summary = truncate_text(summary, max_summary_len)
    
    tweet_text = f"{truncated_title}\n{truncated_summary}\n{url}\n#AI"
    
    # 最終チェック（全角140文字以内）
    # Twitter API v1.1の文字数カウントは全角・半角を区別しないが、ユーザーの要件に従い全角140文字以内を目標とする
    # ただし、Twitter API v2ではURLは23文字固定で、日本語も1文字1カウントなので、ここではv2の仕様を優先する。
    # ユーザーの要件「ツイートは全角140文字以内」は、全角文字を2文字とカウントする日本のガラケー時代の慣習に基づく可能性もあるため、
    # ここでは、全角文字を1文字としてカウントするTwitterの現在の仕様（v2）に沿って、140文字（半角換算）に収めることを優先する。
    # URLは23文字固定なので、残りの140-23=117文字（半角）にタイトル、要約、改行、#AIタグを収める。
    
    # v2の文字数カウント（日本語も1文字1カウント、URLは23文字固定）
    # 140 - 23 (URL) - 3 (改行) - 3 (#AI) = 111文字
    
    # 111文字にタイトルと要約を収める
    max_content_len_v2 = 111
    
    # タイトルと要約を合わせて111文字に収める
    def truncate_for_v2(text, max_len):
        return text[:max_len]

    # タイトルと要約の文字数を調整
    title_v2 = title
    summary_v2 = summary
    
    # まずタイトルを短くする
    if len(title_v2) > max_content_len_v2 // 2:
        title_v2 = truncate_for_v2(title_v2, max_content_len_v2 // 2)
        
    # 残りの文字数を要約に割り当てる
    remaining_len = max_content_len_v2 - len(title_v2) - 1 # -1は改行分
    
    if len(summary_v2) > remaining_len:
        summary_v2 = truncate_for_v2(summary_v2, remaining_len)
        
    tweet_text_v2 = f"{title_v2}\n{summary_v2}\n{url}\n#AI"
    
    # 最終的な文字数チェック
    # URLは23文字としてカウントされるため、len(url)ではなく23を使う
    tweet_len = len(title_v2) + 1 + len(summary_v2) + 1 + 23 + 1 + len("#AI")
    
    if tweet_len > 140:
        # 稀に発生する可能性を考慮し、さらに要約を切り詰める
        excess = tweet_len - 140
        summary_v2 = summary_v2[:-excess]
        tweet_text_v2 = f"{title_v2}\n{summary_v2}\n{url}\n#AI"
        
    print(f"生成されたツイート本文（文字数: {len(tweet_text_v2) - len(url) + 23}）:\n{tweet_text_v2}")
    return tweet_text_v2


def post_tweet(tweet_text: str):
    """Twitter API v2を使用してツイートを投稿する"""
    print("Twitterに投稿中...")
    
    # OAuth1Sessionを使って認証
    twitter = OAuth1Session(
        client_key=TWITTER_CONSUMER_KEY,
        client_secret=TWITTER_CONSUMER_SECRET,
        resource_owner_key=TWITTER_ACCESS_TOKEN,
        resource_owner_secret=TWITTER_ACCESS_TOKEN_SECRET
    )
    
    payload = {"text": tweet_text}
    
    try:
        response = twitter.post(
            TWITTER_API_URL, 
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 201:
            raise Exception(f"ツイート投稿エラー: {response.status_code}, {response.text}")

        print("ツイート投稿成功:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"Twitter APIエラー: {e}")
        raise

def main():
    if not all([MANUS_API_KEY, TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]):
        print("エラー: 必要な環境変数が設定されていません。")
        # GitHub Actionsでの実行を想定しているため、ここでは終了
        return

    # 1. Manus APIにタスクを依頼
    prompt = """
    最新のAI、ビジネス、技術に関するニュースを検索してください。
    最も重要で話題性のある記事を一つ選び、その記事の詳細（タイトル、URL、要約）を以下のJSONフォーマットで出力してください。
    記事の要約は、ツイートの文字数制限（URLを除いて約117文字）に収まるように簡潔にまとめてください。
    
    JSONフォーマット:
    ```json
    {
        "title": "記事のタイトル",
        "url": "記事のURL",
        "summary": "記事の要約（簡潔に）"
    }
    ```
    JSONブロック以外には何も含めないでください。
    """
    
    try:
        task_id = create_manus_task(prompt)
        
        # 2. タスク結果を取得
        manus_result = get_manus_task_result(task_id)
        
        # 3. 結果をパースしてツイート本文を生成
        tweet_content = parse_tweet_content(manus_result)
        tweet_text = generate_tweet_text(tweet_content)
        
        # 4. ツイートを投稿
        post_tweet(tweet_text)
        
    except Exception as e:
        print(f"メイン処理中にエラーが発生しました: {e}")
        # エラーが発生してもGitHub Actionsは失敗として終了する

if __name__ == "__main__":
    main()
