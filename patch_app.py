with open("app.py", "r") as f:
    content = f.read()

import re
new_content = re.sub(r'<<<<<<< HEAD\n=======\n(.*?)>>>>>>> origin/main', r'\1', content, flags=re.DOTALL)

with open("app.py", "w") as f:
    f.write(new_content)
