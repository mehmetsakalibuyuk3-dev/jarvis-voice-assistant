import ast, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

files = ['preload.py', 'jarvis.py', 'speech.py', 'vectordb.py', 'config.py']
all_ok = True
for f in files:
    try:
        with open(f, encoding='utf-8') as fh:
            src = fh.read()
        ast.parse(src)
        print(f'[OK] {f}')
    except SyntaxError as e:
        print(f'[HATA] {f} satir {e.lineno}: {e.msg}')
        all_ok = False
    except FileNotFoundError:
        print(f'[UYARI] {f} bulunamadi (atlanıyor)')

print()
if all_ok:
    print('=== TUM DOSYALAR TEMIZ - SYNTAX HATASI YOK ===')
else:
    print('=== HATALAR VAR - DUZELTILMELI ===')
    sys.exit(1)
