import os

files = [
    'changelog.html',
    'chrome-extension.html',
    'credits.html',
    'download.html',
    'for-educators.html',
    'for-language-learners.html',
    'for-professionals.html',
    'for-readers.html',
    'for-students.html',
    'privacy.html'
]

# Fix index.html
with open('index.html', 'r') as f:
    content = f.read()
content = content.replace(
    '<a class="lp-nav-link" href="#lp-pro" data-section="lp-pro">Pricing</a>\n    <a class="lp-nav-link" href="/download.html">Download</a>',
    '<a class="lp-nav-link" href="#lp-pro" data-section="lp-pro">Pricing</a>\n    <a class="lp-nav-link" href="/chrome-extension.html">Extension</a>\n    <a class="lp-nav-link" href="/download.html">Download</a>'
)
with open('index.html', 'w') as f:
    f.write(content)

# Fix subpages
for file in files:
    with open(file, 'r') as f:
        content = f.read()
    content = content.replace(
        '<a class="site-nav-link" href="/#lp-pro">Pricing</a>\n    <a class="site-nav-link" href="/download.html">Download</a>',
        '<a class="site-nav-link" href="/#lp-pro">Pricing</a>\n    <a class="site-nav-link" href="/chrome-extension.html">Extension</a>\n    <a class="site-nav-link" href="/download.html">Download</a>'
    )
    with open(file, 'w') as f:
        f.write(content)

print("Done")
