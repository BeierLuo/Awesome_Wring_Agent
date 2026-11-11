const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const ui=path.resolve(__dirname,'../ui');
const dom=new JSDOM('<!doctype html><body><div id="view"></div></body>',{runScripts:'outside-only',url:'http://127.0.0.1:8768/'});
const w=dom.window;for(const f of ['vendor/marked.umd.js','vendor/purify.min.js','vendor/katex.min.js','markdown.js'])w.eval(fs.readFileSync(path.join(ui,f),'utf8'));
const el=w.document.getElementById('view');
const source=String.raw`## Method

A **bold** claim with $x_i^2 + y_i^2$ and \(\alpha + \beta\).

$$
\mathcal{L}=\frac{1}{N}\sum_{i=1}^N (p_i-y_i)^2
$$

\[
\begin{aligned}a&=b+c\\d&=e\end{aligned}
\]

| Method | Score |
| --- | --- |
| CLEAR | $0.5$ |

> Verified statement.

- First
- Second

`+'`$not_math$`\n\n```tex\n$$literal$$\n```\n\n'+String.raw`Escaped \$5 and prices $20 and $30 stay readable.`;
w.DraftMarkdown.mount(el,source);
assert.equal(el.querySelector('h2').textContent,'Method');assert.equal(el.querySelector('strong').textContent,'bold');
assert.equal(el.querySelectorAll('.katex').length,5);assert.equal(el.querySelectorAll('.katex-display').length,2);
assert.equal(el.querySelector('pre code').textContent.trim(),'$$literal$$');assert.equal(el.querySelectorAll('code .katex').length,0);
assert.ok(el.querySelector('.markdown-table table'));assert.ok(el.textContent.includes('prices $20 and $30'));
const toggle=el.querySelector('button');toggle.click();assert.equal(el.querySelector('.markdown-source').textContent,source);assert.equal(el.querySelector('.markdown-source').hidden,false);
w.DraftMarkdown.mount(el,source+'\nUpdated');assert.equal(el.querySelector('.markdown-source').hidden,false);toggle.click();assert.equal(el.querySelector('.markdown-source').hidden,true);
const evil=String.raw`<script>window.pwned=1</script><img src=x onerror="window.pwned=2"><iframe src="https://example.com"></iframe><span data-draft-math="0">spoof</span>

[unsafe](javascript:alert(1)) ![remote](https://example.com/tracker.png)

$\href{javascript:alert(1)}{click}$

$\includegraphics{https://example.com/tracker.png}$`;
w.DraftMarkdown.render(el,evil);assert.equal(w.pwned,undefined);assert.equal(el.querySelectorAll('script,img,iframe,form,[onerror]').length,0);assert.equal(el.querySelectorAll('[href^="javascript:"]').length,0);assert.equal(el.querySelectorAll('[data-draft-math]').length,0);
w.DraftMarkdown.render(el,String.raw`Bad $\frac{1}{$ and good $x+1$`);assert.ok(el.querySelector('.katex-error'));assert.ok(el.textContent.includes('good'));
w.DraftMarkdown.render(el,String.raw`$\gdef\foo{123}\foo$ then $\foo$`);assert.equal(el.querySelectorAll('.katex-html')[1].textContent,'\\foo','macros cannot leak across formulas');
console.log('PASS: Markdown, four math delimiters, table math, code/escaped dollars, source round-trip, invalid formulas, macro isolation and XSS/remote-resource protection.');dom.window.close();
