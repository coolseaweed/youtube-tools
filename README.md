# YouTube Multi-Language Caption Uploader

YouTube 영상 업로드 및 다국어 자막 일괄 업로드 도구

## 기능

- 영상 업로드 + 자막 일괄 추가
- 기존 영상에 자막만 추가
- 파일명 기반 언어 자동 인식 (ko.srt → 한국어)

## 설치

```bash
pip install -r requirements.txt
```

## 사전 준비 (Google Cloud)

1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. 프로젝트 생성
3. YouTube Data API v3 활성화
4. OAuth 동의 화면 설정
   - 테스트 사용자에 본인 이메일 추가
5. 사용자 인증 정보 > OAuth 클라이언트 ID 생성 (데스크톱 앱)
6. `client_secrets.json` 다운로드 후 프로젝트 루트에 저장

## 사용법

```bash
# 영상 업로드 + 자막 일괄 추가
python upload.py video.mp4 "영상 제목" --captions ./captions/

# 기존 영상에 자막만 추가
python upload.py --video-id "VIDEO_ID" --captions ./captions/

# 옵션
python upload.py video.mp4 "제목" --captions ./captions/ \
    --description "영상 설명" \
    --privacy private  # public, unlisted, private
```

## 자막 폴더 구조

```
captions/
├── ko.srt    # 한국어
├── en.srt    # 영어
├── ja.srt    # 일본어
├── zh.srt    # 중국어
├── es.srt    # 스페인어
├── fr.srt    # 프랑스어
├── de.srt    # 독일어
├── pt.srt    # 포르투갈어
├── vi.srt    # 베트남어
└── ...       # 파일명 = ISO 639-1 언어코드
```

## 지원 언어 코드

| 코드 | 언어         | 코드 | 언어       |
| ---- | ------------ | ---- | ---------- |
| ko   | 한국어       | en   | 영어       |
| ja   | 일본어       | zh   | 중국어     |
| es   | 스페인어     | fr   | 프랑스어   |
| de   | 독일어       | pt   | 포르투갈어 |
| it   | 이탈리아어   | ru   | 러시아어   |
| vi   | 베트남어     | th   | 태국어     |
| id   | 인도네시아어 | ar   | 아랍어     |
| hi   | 힌디어       | tr   | 터키어     |

전체 언어 코드: [ISO 639-1](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes)

## License

MIT
