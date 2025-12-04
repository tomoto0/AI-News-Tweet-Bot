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
        # APIのレスポンスが 'id' または 'task_id' のどちらで返ってくるか不明なため、両方試す
        task_id = task_data.get("id")
        # ユーザーのエラーログから、task_idが最上位のキーとして返されていることが確認されたが、
        # それはタスク作成が成功していない場合のレスポンス構造である可能性が高い。
        # 成功時のレスポンス構造を優先し、'id'がない場合にのみ'task_id'を試す。
        # ただし、エラーメッセージにあるように 'task_id' が返されている場合はそれをIDとして使用する。
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
    
    # タイムアウト設定（例：5分）
    timeout = 300
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(task_url, headers=headers)
            response.raise_for_status()
            task_data = response.json()
            
            status = task_data.get("status")
            print(f"現在のステータス: {status}")

            if status == "completed":
                messages = task_data.get("messages", [])
                # 最後のメッセージがAIの応答
                # ユーザーの添付画像から、JSONが生成された後、タスクが完了していない可能性があるため、
                # 最後のメッセージがJSONを含んでいるかを確認する
                if messages:
                    result_text = messages[-1].get("text", "")
                    if result_text and ("```json" in result_text or "{" in result_text and "}" in result_text):
                        print("タスク完了。結果を取得しました。")
                        return result_text
                
                # JSONが見つからない場合は、まだ処理中と見なしてポーリングを続けるか、エラーとする
                print("タスクは完了しましたが、期待するJSON結果が見つかりません。5秒待機して再試行します...")
                time.sleep(5)

            elif status in ["pending", "running"]:
                print("5秒待機します...")
                time.sleep(5)
            else:
                raise Exception(f"タスクが失敗または不明なステータスになりました: {status}, 詳細: {task_data}")
        except requests.exceptions.RequestException as e:
            print(f"Manus APIタスク結果取得エラー: {e}")
            raise
        except Exception as e:
            print(f"タスク処理エラー: {e}")
            raise
    
    raise Exception("タスク結果の取得がタイムアウトしました。")


def parse_tweet_content(manus_result: str) -> dict:
    """Manusの結果からツイート内容をパースする"""
    print("Manusの結果をパース中...")
    try:
        # JSONブロックを抽出
        start = manus_result.find("```json")
        if start != -1:
            start += len("```json")
            end = manus_result.rfind("```")
            if end != -1 and start < end:
                json_str = manus_result[start:end].strip()
            else:
                # 閉じタグがない場合は、開始タグ以降をJSONと見なす
                json_str = manus_result[start:].strip()
        else:
            # JSONブロックが見つからない場合、結果全体がJSONであると仮定
            print("JSONブロックが見つかりません。結果全体をJSONとしてパースします。")
            json_str = manus_result
        
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
    
    # v2の文字数カウント（日本語も1文字1カウント、URLは23文字固定）
    # 140 - 23 (URL) - 3 (改行) - 3 (#AI) = 111文字
    max_content_len_v2 = 111
    
    def truncate_for_v2(text, max_len):
        return text[:max_len]

    # タイトルと要約を合わせて111文字に収める
    title_v2 = title
    summary_v2 = summary
    
    if len(title_v2) + len(summary_v2) + 1 > max_content_len_v2:
        # タイトルを優先し、残りを要約に割り当てる
        max_summary_len = max_content_len_v2 - len(title_v2) - 1
        if max_summary_len < 10: # 要約が短すぎる場合はタイトルも削る
            max_title_len = max_content_len_v2 // 2
            title_v2 = truncate_for_v2(title, max_title_len)
            max_summary_len = max_content_len_v2 - len(title_v2) - 1
        
        summary_v2 = truncate_for_v2(summary, max_summary_len)

    tweet_text_v2 = f"{title_v2}\n{summary_v2}\n{url}\n#AI"
    
    # 最終的な文字数チェック
    tweet_len = len(title_v2) + 1 + len(summary_v2) + 1 + 23 + 1 + len("#AI")
    
    if tweet_len > 140:
        # さらに要約を切り詰める
        excess = tweet_len - 140
        summary_v2 = summary_v2[:-excess]
        tweet_text_v2 = f"{title_v2}\n{summary_v2}\n{url}\n#AI"
        
    print(f"生成されたツイート本文（推定文字数: {len(tweet_text_v2) - len(url) + 23}）:\n{tweet_text_v2}")
    return tweet_text_v2


def post_tweet(tweet_text: str):
    """Twitter API v2を使用してツイートを投稿する"""
    print("Twitterに投稿中...")
    
    # Twitter API v2の投稿にはOAuth 1.0a User Contextが必要
    # client_key, client_secret, resource_owner_key, resource_owner_secret の順で渡す
    twitter = OAuth1Session(
        client_key=TWITTER_CONSUMER_KEY,
        client_secret=TWITTER_CONSUMER_SECRET,
        resource_owner_key=TWITTER_ACCESS_TOKEN,
        resource_owner_secret=TWITTER_ACCESS_TOKEN_SECRET
    )
    
    payload = {"text": tweet_text}
    
    try:
        response = twitter.post(TWITTER_API_URL, json=payload)
        
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
        return

    prompt = '''
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
    JSONブロックを生成したら、他の応答はせず、タスクを完了してください。
    '''
    
    try:
        task_id = create_manus_task(prompt)
        manus_result = get_manus_task_result(task_id)
        tweet_content = parse_tweet_content(manus_result)
        tweet_text = generate_tweet_text(tweet_content)
        post_tweet(tweet_text)
        
    except Exception as e:
        print(f"メイン処理中にエラーが発生しました: {e}")
        # エラーで終了させるために1を返す
        exit(1)

if __name__ == "__main__":
    main()

