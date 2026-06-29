import os
import re
import hashlib
import sqlite3
from flask import Flask, request, jsonify, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# Nginx などのリバースプロキシの背後で動作するための設定
# X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-Prefix を信頼する
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')
FIXED_SALT_BASE = "td_secret_salt_2026_"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS high_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                score INTEGER NOT NULL,
                wave INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

# templates/index.html の末尾の <script> タグのコード文字数（空白・改行除く）を数えて Salt を動的生成する
_cached_salt = None

def get_dynamic_salt():
    global _cached_salt
    # 本番環境ではキャッシュを利用するが、開発環境(debug)では毎回再計算する
    if _cached_salt and not app.debug:
        return _cached_salt

    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
    if not os.path.exists(template_path):
        # テンプレートファイルが見つからない場合はフォールバック
        return FIXED_SALT_BASE + "0"

    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            html = f.read()

        # すべての <script> ... </script> の中身を抽出
        matches = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
        if not matches:
            return FIXED_SALT_BASE + "0"

        # 最後のスクリプトタグ（メインのゲームロジック）の内容を取得
        script_content = matches[-1]

        # 改行・タブ・スペースなどを完全に除去して文字数のズレを防ぐ
        # JavaScript側の .replace(/[ \f\n\r\t\v]/g, "") と一致させる
        clean_content = re.sub(r'[ \f\n\r\t\v]+', '', script_content)
        length = len(clean_content)

        _cached_salt = FIXED_SALT_BASE + str(length)
        return _cached_salt
    except Exception as e:
        app.logger.error(f"Error calculating dynamic salt: {e}")
        return FIXED_SALT_BASE + "error"

def clean_expired_scores(conn):
    """1週間以上経過した古いハイスコアを削除する"""
    conn.execute("DELETE FROM high_scores WHERE created_at < datetime('now', '-7 days')")
    conn.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/high_scores', methods=['GET'])
def get_high_scores():
    try:
        conn = get_db()
        # 古いデータのクリーンアップ
        clean_expired_scores(conn)
        
        # 上位5件を取得
        cursor = conn.execute(
            "SELECT score, wave, created_at FROM high_scores ORDER BY score DESC, created_at ASC LIMIT 5"
        )
        rows = cursor.fetchall()
        
        high_scores = []
        for row in rows:
            high_scores.append({
                "score": row["score"],
                "wave": row["wave"],
                "created_at": row["created_at"]
            })
            
        return jsonify(high_scores)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/high_scores', methods=['POST'])
def submit_high_score():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request body"}), 400

        score = data.get("score")
        wave = data.get("wave")
        client_hash = data.get("hash")

        # 1. 基本バリデーション
        if score is None or wave is None or not client_hash:
            return jsonify({"error": "Missing required fields"}), 400

        try:
            score = int(score)
            wave = int(wave)
        except ValueError:
            return jsonify({"error": "Score and Wave must be integers"}), 400

        if score < 0 or wave < 0:
            return jsonify({"error": "Score and Wave must be non-negative"}), 400

        # 2. 簡易チート対策: スコアの現実的上限チェック
        max_possible_score = wave * 15000 + 5000
        if score > max_possible_score:
            return jsonify({"error": "Score exceeds theoretical maximum for this wave"}), 400

        # 3. 簡易チート対策: ハッシュ検証
        salt = get_dynamic_salt()
        raw_str = f"{score}{wave}{salt}"
        server_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

        if client_hash.lower() != server_hash.lower():
            return jsonify({"error": "Integrity check failed (hash mismatch)"}), 400

        # 4. データベースへの登録
        conn = get_db()
        clean_expired_scores(conn)
        
        conn.execute(
            "INSERT INTO high_scores (score, wave) VALUES (?, ?)",
            (score, wave)
        )
        conn.commit()

        # 最新のランキングを返す
        cursor = conn.execute(
            "SELECT score, wave, created_at FROM high_scores ORDER BY score DESC, created_at ASC LIMIT 5"
        )
        rows = cursor.fetchall()
        
        high_scores = []
        for row in rows:
            high_scores.append({
                "score": row["score"],
                "wave": row["wave"],
                "created_at": row["created_at"]
            })
            
        return jsonify(high_scores)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # データベースの初期化
    init_db()
    # 開発サーバーの起動
    app.run(host='127.0.0.1', port=5000, debug=True)
