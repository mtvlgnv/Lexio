import os
import glob

static_dir = '/Users/mtvlgnv/Lexio/product/static'
html_files = glob.glob(os.path.join(static_dir, '*.html'))

for html_file in html_files:
    with open(html_file, 'r') as f:
        content = f.read()
    
    # We only want to replace the img tag src, not the link rel="icon" ones.
    # The link tags look like: <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png?v=2" />
    # The img tags look like: <img src="/favicon-32.png?v=2"
    new_content = content.replace('<img src="/favicon-32.png', '<img src="/favicon-180.png')
    
    if new_content != content:
        with open(html_file, 'w') as f:
            f.write(new_content)
        print(f"Updated {html_file}")

