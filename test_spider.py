import os
import re
import pprint
import requests
from bs4 import BeautifulSoup
headers = {
    'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
    'Accept': 'application/json, application/vnd.github+json',
    'Host': 'api.github.com',
    'Connection': 'keep-alive'
}
payload = {}


def get_commit_info_api(repo_owner, repo_name, commit_sha):
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{commit_sha}"
    response = requests.get(api_url)
    return response.json()

content = get_commit_info_api('curl', 'curl', 'aeb1a281cab13c7ba791cb104e556b20e713941f')
pprint.pprint(content)

def commit_parse(url):
    try:
        # 个性化处理commit页面的url
        detail_url = github_url_transfer(url).replace('commit', 'commits')
        headers['Accept'] = 'application/json, application/vnd.github+json'
        response = requests.request("GET", detail_url, headers=headers, data=payload)
        commit_info = response.json()
        # 分别存储message，deletion和addition的数目，改了哪几个文件（文件名称，修改和删除数目，blob_url—）,diff信息
        commit_content = {
            'message': commit_info['commit']['message'].strip(),
            'changes': commit_info['stats'],
            'files': [],
        }
        for file in commit_info['files']:
            file_detail = {
                'filename': file['filename'],
                'additions': file['additions'],
                'deletions': file['deletions'],
                'blob_url': file['blob_url'],
                'diff': None
            }
            # 如果没有任何修改，说明这文件没改，没有diff
            if file['changes'] != 0:
                file_detail['diff'] = file['patch']
            commit_content['files'].append(file_detail)
        print(commit_content)
        return commit_content
    except Exception as e:
        print(e)
        return None