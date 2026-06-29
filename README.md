# Free-Placement Tower Defense (Flask App)

ハイスコア記録機能付きのタワーディフェンスゲームの Flask アプリケーションです。
nginx リバースプロキシの裏で動作するように設計されています。

## 特徴

- **ハイスコアランキング機能**: 
  - 過去1週間（7日間）のスコアの上位5位までを記録・表示します。
  - 1週間を過ぎた古いスコアは自動的に削除されます。
  - プレイヤー名の入力は不要で、ゲームオーバー時にスコアが自動登録されます。
- **簡易チート対策**:
  1. **動的 Salt によるハッシュ検証**: ゲームを実行する `<script>` タグのコード内容（空白・改行を除外）の文字数をカウントし、それを固定文字列と組み合わせた値を Salt（ソルト）とします。クライアント側で `score + wave + Salt` の SHA-256 ハッシュ値を計算し、送信時に検証します。これにより、コードを目で見ただけでは Salt が判別しづらくなっています。
  2. **スコアの上限値チェック**: Wave ごとの論理的な最高スコアの検証を行い、極端に不可能なスコアを弾きます。
- **リバースプロキシ対応**:
  - Werkzeug の `ProxyFix` を導入しており、Nginx の裏でもプロトコル、ホスト、プレフィックス（サブパス）が正しく認識されます。
  - フロントエンドの通信やリンクは相対パスで設計されています。

## 開発環境のセットアップと起動方法

本プロジェクトでは `uv` を使用して Python 環境を管理します。

1. **仮想環境の作成**
   ```bash
   uv venv
   ```

2. **仮想環境の有効化**
   - **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\activate
     ```
   - **Linux / macOS**:
     ```bash
     source .venv/bin/activate
     ```

3. **依存パッケージのインストール**
   ```bash
   uv pip install Flask
   ```

4. **ローカルサーバーの起動**
   ```bash
   python app.py
   ```
   起動後、ブラウザで `http://127.0.0.1:5000` にアクセスしてください。

## 本番環境へのデプロイ方法

### 1. アプリケーションサーバー (Gunicorn 等) の使用
本番環境では Flask の開発用サーバーではなく、`gunicorn` などの WSGI サーバーを使用してください。

**Gunicorn のインストールと起動例:**
```bash
uv pip install gunicorn
gunicorn -w 4 -b 127.0.0.1:5000 app:app
```

### 2. Nginx リバースプロキシの設定

nginx がリクエストヘッダー（プロトコル、IP、ホスト名、および必要に応じてサブパス）を Flask へ引き渡すように設定します。

#### パターンA: ルートパス (`/`) で公開する場合
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### パターンB: 特定のサブパス（例: `/td/`）で公開する場合
サブパスで公開する場合、nginx 側の設定で `X-Forwarded-Prefix` を設定するだけで Flask がパスを自動的に補正します。

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location /td/ {
        proxy_pass http://127.0.0.1:5000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /td;
    }
}
```
