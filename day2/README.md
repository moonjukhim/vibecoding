### MCP 서버를 만드는 방법

1. 개발 환경 구축

- uv 설치

```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

- FastMCP 설치

```bash
pip install fastmcp
python -m pip install --upgrade --force-reinstall fastmcp
```

```bash
fastmcp version
```


2. MCP 서버 프로젝트 구조

```text
C:\
└─ MCP
   └─ Datetime-MCP
      └─ server.py
```

- server.py 파이썬 파일

```python
from fastmcp import FastMCP
from datetime import datetime

mcp = FastMCP(name="Datetime-MCP")

@mcp.tool()
def get_current_datetime() -> str:
    """현재 날짜와 시각을 반환합니다."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    mcp.run()
```

```bash
python -m venv venv
.\venv\Scripts\activate
pip install fastmcp
fastmcp install claude-desktop server.py
```

```text
Datetime-MCP 서버를 사용하여 현재 날짜를 알려줘.
```