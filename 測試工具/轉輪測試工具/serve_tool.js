'use strict';
const http = require('http'), fs = require('fs'), path = require('path');
const root = fs.realpathSync(__dirname);
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css','.png':'image/png','.json':'application/json','.atlas':'text/plain','.skel':'application/octet-stream'};
const server = http.createServer((req, res) => {
    try {
        const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const file = path.resolve(root, '.' + (pathname === '/' ? '/slot_test.html' : pathname));
        const relative = path.relative(root, fs.realpathSync(file));
        if(relative.startsWith('..') || path.isAbsolute(relative) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; }
        res.writeHead(200, {'Content-Type':mime[path.extname(file)] || 'application/octet-stream'});
        const stream = fs.createReadStream(file); stream.on('error', () => res.destroy()); stream.pipe(res);
    } catch (_) { res.writeHead(404); res.end(); }
});
server.listen(0, '127.0.0.1', () => console.log(`Open http://127.0.0.1:${server.address().port}/slot_test.html\nPress Ctrl+C to stop.`));
server.on('error', err => { console.error(err.message); process.exitCode = 1; });
