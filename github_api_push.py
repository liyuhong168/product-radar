"""通过GitHub API推送文件到仓库（绕过git push超时问题）
用法: python3 github_api_push.py "commit message"
"""
import json, os, sys, base64
import urllib.request

REPO = 'liyuhong168/product-radar'
BRANCH = 'main'

def get_token():
    with open(os.path.expanduser('~/.git-credentials')) as f:
        return f.read().strip().split('ghp_')[1].split('@')[0]

def api(method, path, data=None):
    token = get_token()
    headers = {'Authorization': f'token ghp_{token}', 'Content-Type': 'application/json', 'User-Agent': 'hermes'}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f'https://api.github.com{path}', headers=headers, data=body)
    if method != 'POST':
        req.get_method = lambda: method
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

def push_files(files, message):
    """推送指定文件列表到GitHub"""
    ref = api('GET', f'/repos/{REPO}/git/refs/heads/{BRANCH}')
    head_sha = ref['object']['sha']
    commit = api('GET', f'/repos/{REPO}/git/commits/{head_sha}')
    base_tree = commit['tree']['sha']

    # Upload blobs in batches of 5
    tree_items = []
    batch = []
    for rel_path, abs_path in files:
        if not os.path.exists(abs_path):
            continue
        batch.append((rel_path, abs_path))
        if len(batch) >= 5:
            tree_items.extend(_upload_batch(batch))
            batch = []
    if batch:
        tree_items.extend(_upload_batch(batch))

    if not tree_items:
        print('  无变更')
        return

    # Create tree
    tree = api('POST', f'/repos/{REPO}/git/trees', {'base_tree': base_tree, 'tree': tree_items})
    # Create commit
    new_commit = api('POST', f'/repos/{REPO}/git/commits', {
        'message': message, 'tree': tree['sha'], 'parents': [head_sha]
    })
    # Update ref
    api('PATCH', f'/repos/{REPO}/git/refs/heads/{BRANCH}', {'sha': new_commit['sha']})
    print(f'  ✅ 已部署 {len(tree_items)} 个文件')

def _upload_batch(batch):
    items = []
    for rel_path, abs_path in batch:
        with open(abs_path, 'rb') as f:
            content = f.read()
        blob = api('POST', f'/repos/{REPO}/git/blobs',
                   {'content': base64.b64encode(content).decode(), 'encoding': 'base64'})
        items.append({'path': rel_path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    return items

if __name__ == '__main__':
    base = '/home/lee/product-radar'
    files = []

    import glob
    for subdir in ('data/channels', 'data/history', 'data/discovery', 'output'):
        full = os.path.join(base, subdir)
        if not os.path.isdir(full):
            continue
        all_files = sorted(os.listdir(full))
        for f in all_files[-12:]:
            if not f.endswith('.json') and not f.endswith('.html'):
                continue
            files.append((f'{subdir}/{f}', os.path.join(full, f)))

    # Always-push files
    for f in ('output/platform.html', 'output/index.html', 'status.json'):
        fp = os.path.join(base, f)
        if os.path.exists(fp):
            files.append((f, fp))

    msg = sys.argv[1] if len(sys.argv) > 1 else 'auto-push'
    push_files(files, msg)
