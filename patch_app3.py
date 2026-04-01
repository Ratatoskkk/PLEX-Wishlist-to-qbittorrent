with open("app.py", "r") as f:
    ap = f.read()

ap = ap.replace('''<<<<<<< HEAD

=======
>>>>>>> origin/main''', '')

with open("app.py", "w") as f:
    f.write(ap)
