# -*- coding: utf-8 -*-
"""kitae.config.json 로드/저장과 경로 해석.

설정은 저장소 루트의 `kitae.config.json` 하나로 모은다. 경로는 상대로 적어도
되고, 저장소 루트 기준으로 해석된다 — 다른 사람이 클론해도 그대로 돌아간다.

언어는 `languages`에 키로 나열하고(`ja`, `ko`, `en`, …), `source`가 원문,
`target`이 지금 작업 중인 언어다. 번역 데이터는 항목마다 이 키들을 갖는다.
"""
import json
import os

CONFIG_NAME = "kitae.config.json"

DEFAULTS = {
    "orig_dir": "",                       # 원본 GDI 덤프가 있는 디렉터리
    "out_dir": "dist",                    # 빌드 결과
    "work_dir": "work",                   # 중간 산출물 (git 제외)
    "languages": ["ja", "ko"],
    "source": "ja",
    "target": "ko",
    "font": {
        "ttf": "",                        # 한글 글리프를 뽑을 TTF/OTF
        "size": 21,
        "y_offset": 2,
        # 글리프를 넣을 리드바이트 페이지 (JIS 2수준 — 이 게임이 거의 안 쓴다)
        "pages": [0xEE, 0xED, 0xE1, 0x9B, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6,
                  0xE7, 0xE8, 0xE9, 0xEA, 0xE0, 0x9C, 0x9D, 0x9E, 0x9F],
    },
    "scripts": ["KOTORI_01"],             # 작업 대상 시나리오
}


def repo_root(start=None):
    """kitae.config.json 이 있는 가장 가까운 상위 디렉터리."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(d, CONFIG_NAME)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            # 설정이 아직 없으면 패키지 상위를 루트로 본다 (init 전 상태)
            return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = parent


class Config(dict):
    """설정 + 경로 해석. dict 처럼 쓰되 `path()` 로 절대경로를 얻는다."""

    def __init__(self, data=None, root=None):
        super().__init__()
        self.root = root or repo_root()
        merged = json.loads(json.dumps(DEFAULTS))
        merged.update(data or {})
        self.update(merged)

    # ---------------------------------------------------------------- io
    @classmethod
    def load(cls, root=None):
        root = root or repo_root()
        p = os.path.join(root, CONFIG_NAME)
        data = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        return cls(data, root)

    def save(self):
        p = os.path.join(self.root, CONFIG_NAME)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dict(self), f, ensure_ascii=False, indent=2)
            f.write("\n")
        return p

    @property
    def exists(self):
        return os.path.exists(os.path.join(self.root, CONFIG_NAME))

    # -------------------------------------------------------------- paths
    def path(self, *parts):
        """설정값이나 상대경로를 저장소 루트 기준 절대경로로."""
        first = parts[0] if parts else ""
        if os.path.isabs(first):
            return os.path.join(*parts)
        return os.path.join(self.root, *parts)

    def dir(self, key):
        return self.path(self.get(key) or DEFAULTS.get(key, ""))

    @property
    def data_dir(self):
        return self.path("data")

    @property
    def translation_dir(self):
        return self.path("translation")

    def track(self, n=3):
        """원본 덤프의 트랙 파일 경로."""
        d = self.dir("orig_dir")
        if not d or not os.path.isdir(d):
            return None
        for name in sorted(os.listdir(d)):
            if name.lower().endswith(f"track{n:02d}.bin") or \
               name.lower().endswith(f"track{n:02d}.raw"):
                return os.path.join(d, name)
        return None

    def gdi(self):
        d = self.dir("orig_dir")
        if not d or not os.path.isdir(d):
            return None
        for name in sorted(os.listdir(d)):
            if name.lower().endswith(".gdi"):
                return os.path.join(d, name)
        return None

    # ----------------------------------------------------------- language
    def check_lang(self, lang):
        if lang not in self["languages"]:
            raise SystemExit(
                f"'{lang}' 은 설정된 언어가 아닙니다. languages={self['languages']}")
        return lang
