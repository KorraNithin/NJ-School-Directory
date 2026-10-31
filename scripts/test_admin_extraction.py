
import requests
from bs4 import BeautifulSoup
import re

URL = "https://www.njsbjc.org/district/leadership-team"

response = requests.get(
    URL,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=25
)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

for tag in soup(["script", "style", "nav", "footer", "header"]):
    tag.decompose()

# Extract text and split into lines
text = soup.get_text("\n", strip=True)
lines = [line.strip() for line in text.splitlines() if line.strip()]

TITLE_PATTERN = re.compile(
    r"(Superintendent|Chief of Operations|Business Administrator|"
    r"Director of Curriculum and Assessment|Director of Special Projects.*|"
    r"Clinical Director|Administrative Assistant.*|"
    r"Director of District Transition.*)",
    re.IGNORECASE
)

print("\nVERIFIED ADMINISTRATOR CANDIDATES")
print("=" * 60)

for line in lines:
    match = TITLE_PATTERN.search(line)

    if not match:
        continue

    title = match.group(0).strip()
    name = line[:match.start()].strip(" ,:-")

    # Ignore lines that do not look like a person's name
    if len(name.split()) < 2:
        continue

    if not re.search(r"[A-Za-z]", name):
        continue

    print("\nName:", name)
    print("Title:", title)

print("\nSource:", URL)
