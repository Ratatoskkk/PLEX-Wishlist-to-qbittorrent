import re

with open('test_downloader.py', 'r') as f:
    content = f.read()

# Replace the conflict markers and keep both updated versions
new_content = re.sub(r'<<<<<<< Updated upstream(.*?)\n=======(.*?)\n>>>>>>> Stashed changes', r'\1\n\2', content, flags=re.DOTALL)

with open('test_downloader.py', 'w') as f:
    f.write(new_content)
