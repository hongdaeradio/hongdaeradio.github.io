#!/usr/bin/env python3
"""
홍대라디오 랜딩 페이지 자동 업데이트 스크립트
- 구독자 수 + 날짜
- 총 조회수
- New Uploaded 최신 3개 (영상별 조회수 포함)
"""
import json, re, sys, os
from urllib.request import urlopen, Request
from datetime import datetime, timezone, timedelta

API_KEY = os.environ['YT_API_KEY']
CHANNEL_ID = os.environ['YT_CHANNEL_ID']
KST = timezone(timedelta(hours=9))

def api_get(url):
    req = Request(url)
    with urlopen(req) as r:
        return json.loads(r.read())

# 1. 채널 통계 (구독자 수, 총 조회수)
ch = api_get(f'https://www.googleapis.com/youtube/v3/channels?part=statistics&id={CHANNEL_ID}&key={API_KEY}')
stats = ch['items'][0]['statistics']
subscriber_count = stats['subscriberCount']
total_views = stats['viewCount']

# 2. 최신 영상 3개 조회
search = api_get(f'https://www.googleapis.com/youtube/v3/search?key={API_KEY}&channelId={CHANNEL_ID}&part=snippet&order=date&maxResults=3&type=video')
video_ids = [item['id']['videoId'] for item in search['items']]
video_snippets = {item['id']['videoId']: item['snippet'] for item in search['items']}

# 3. 영상별 조회수 조회
ids_str = ','.join(video_ids)
vid_stats = api_get(f'https://www.googleapis.com/youtube/v3/videos?key={API_KEY}&id={ids_str}&part=statistics,contentDetails')
video_views = {}
video_durations = {}
for item in vid_stats['items']:
    video_views[item['id']] = int(item['statistics']['viewCount'])
    # ISO 8601 duration → minutes
    dur = item['contentDetails']['duration']  # PT1H28M30S
    hours = int(re.search(r'(\d+)H', dur).group(1)) if 'H' in dur else 0
    mins = int(re.search(r'(\d+)M', dur).group(1)) if 'M' in dur else 0
    video_durations[item['id']] = hours * 60 + mins

# 4. index.html 읽기
with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

today = datetime.now(KST).strftime('%Y년 %m월 %d일')

# 5. 구독자 수 업데이트
html = re.sub(
    r'🎧 .*구독자 수 : .*명\+',
    f'🎧 {today} 구독자 수 : {subscriber_count}명+',
    html
)

# 6. 총 조회수 삽입/업데이트 (구독자 수 바로 아래)
total_views_line = f'<p class="subscriber-count" style="font-size:0.85em;margin-top:2px;opacity:0.8;">Total 🎧 {int(total_views):,} plays</p>'
if 'Total 🎧' in html:
    html = re.sub(r'<p class="subscriber-count"[^>]*>Total 🎧.*?</p>', total_views_line, html)
else:
    # 구독자 수 라인 바로 뒤에 삽입
    html = re.sub(
        r'(🎧 .*구독자 수 : .*명\+</p>)',
        lambda m: m.group(1) + '\n  ' + total_views_line,
        html
    )

# 7. New Uploaded 영상 3개 교체
# 기존 video-card 블록 찾기 (New Uploaded 섹션)
new_uploaded_pattern = r'(▸ New Uploaded</p>\s*<div class="video-grid">)(.*?)(</div>\s*<p class="sub-section-label">▸ Coming Soon)'
match = re.search(new_uploaded_pattern, html, re.DOTALL)

if match:
    cards_html = ''
    for vid in video_ids:
        snippet = video_snippets[vid]
        # 타이틀에서 이모지+채널명 제거: "📚 Title | Description | 📻 Hongdae Radio" → "Title"
        full_title = snippet['title'].replace('&amp;', '&')
        # | 기준으로 분리, 첫 번째 파트만
        parts = full_title.split('|')
        title_part = parts[0].strip()
        desc_part = parts[1].strip() if len(parts) > 1 else ''
        # 이모지 제거 (선두)
        title_clean = re.sub(r'^[\U0001f300-\U0001f9ff\u2600-\u27bf\ufe0f\s]+', '', title_part).strip()
        desc_clean = re.sub(r'^[\U0001f300-\U0001f9ff\u2600-\u27bf\ufe0f\s]+', '', desc_part).strip()

        pub_date = snippet['publishedAt'][:10].replace('-', '.')
        views = video_views.get(vid, 0)
        duration = video_durations.get(vid, 0)
        dur_str = f'{duration}min' if duration > 0 else ''

        # 썸네일: YouTube 고화질
        thumb_url = f'https://img.youtube.com/vi/{vid}/hqdefault.jpg'

        meta_parts = []
        if desc_clean:
            meta_parts.append(desc_clean)
        if dur_str:
            meta_parts.append(dur_str)
        meta_str = ' · '.join(meta_parts)

        cards_html += f'''
    <a class="video-card" href="https://youtu.be/{vid}" data-ytid="{vid}" target="_blank" rel="noopener">
      <div class="video-thumb"><img src="{thumb_url}" alt="{title_clean}" /></div>
      <div class="video-info">
        <p class="video-title">{title_clean}</p>
        <p class="video-meta">{meta_str}</p>
        <p class="video-date">{pub_date} · 🎧 {views:,} plays</p>
      </div>
    </a>'''

    html = re.sub(
        new_uploaded_pattern,
        lambda m: m.group(1) + cards_html + '\n  ' + m.group(3),
        html,
        flags=re.DOTALL
    )

# 8. 플레이리스트 자동 갱신 (ALL_PLAYLISTS 배열)
FULL_COLLECTION_ID = 'PLBIn_rMVsvR7G7UydGECeXJuFC2YFagUI'
playlists = api_get(f'https://www.googleapis.com/youtube/v3/playlists?key={API_KEY}&channelId={CHANNEL_ID}&part=snippet&maxResults=50')

pl_entries = []
for item in playlists['items']:
    pid = item['id']
    if pid == FULL_COLLECTION_ID:
        continue  # Full Collection은 고정 카드로 별도 표시
    title = item['snippet']['title']
    desc = item['snippet'].get('description', '').split('\n')[0][:40]
    # 이모지 추출 (타이틀 맨 앞) — 국기 이모지 등 포함
    emoji_match = re.match(r'^((?:[\U0001f1e0-\U0001f1ff]{2}|[\U0001f300-\U0001f9ff\u2600-\u27bf\ufe0f\u200d])+)\s*', title)
    emoji = emoji_match.group(1) if emoji_match else '🎵'
    name = title[len(emoji_match.group(0)):].strip() if emoji_match else title
    url = f'https://www.youtube.com/playlist?list={pid}'
    pl_entries.append({'emoji': emoji, 'name': name, 'desc': desc, 'url': url})

# ALL_PLAYLISTS JS 배열 교체
if pl_entries:
    js_items = []
    for p in pl_entries:
        # JS 문자열 이스케이프
        name_js = p['name'].replace("'", "\\'")
        desc_js = p['desc'].replace("'", "\\'")
        js_items.append(
            f"  {{ emoji: \"{p['emoji']}\", name: \"{name_js}\", desc: \"{desc_js}\", url: \"{p['url']}\" }}"
        )
    new_array = 'const ALL_PLAYLISTS = [\n' + ',\n'.join(js_items) + ',\n];'
    html = re.sub(
        r'const ALL_PLAYLISTS = \[.*?\];',
        new_array,
        html,
        flags=re.DOTALL
    )
    print(f'  Playlists updated: {len(pl_entries)} items (excl. Full Collection)')

# 9. 저장
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'✅ Updated: subscribers={subscriber_count}, total_views={total_views}, videos={len(video_ids)}')
for vid in video_ids:
    s = video_snippets[vid]
    print(f'  - {vid}: {s["title"][:40]}... ({video_views.get(vid,0)} views)')
