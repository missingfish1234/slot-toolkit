'use strict';

const MANIFEST = '.psd-export-manifest.json';
const JOURNAL = '.psd-export-transaction.json';

function safeDocumentName(value) {
    const name = String(value || 'Untitled').replace(/\.(psd|psb)$/i, '')
        .replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/[. ]+$/, '');
    return /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name) ? `PSD_${name}` : (name || 'Untitled');
}

async function child(folder, name) {
    return (await folder.getEntries()).find(entry => entry.name.toLowerCase() === name.toLowerCase()) || null;
}

async function filesIn(folder, prefix = '') {
    const files = [];
    for (const entry of await folder.getEntries()) {
        const path = prefix + entry.name;
        if (entry.isFolder) files.push(...await filesIn(entry, path + '/'));
        else files.push(path);
    }
    return files;
}

function documentSourceId(doc, sessionId) {
    let path = '';
    try { path = String(doc.path || '').trim(); } catch (_) { /* Unsaved documents may have no path. */ }
    if (path) {
        path = path.replace(/\\/g, '/');
        if (/^[a-z]:\//i.test(path) || path.startsWith('//')) path = path.toLowerCase();
        return 'path:' + path;
    }
    if (!sessionId || doc.id == null) throw new Error('無法辨識來源 PSD，請先儲存文件後重試。');
    return `unsaved:${sessionId}:${doc.id}`;
}

async function previousManifest(root, targetName, documentName, sourceId) {
    const existing = await child(root, targetName);
    if (!existing) return null;
    if (!existing.isFolder) throw new Error(`目的位置不是資料夾：${targetName}`);
    const previousFile = await child(existing, MANIFEST);
    if (!previousFile) throw new Error(`目的資料夾沒有工具產物清單，已保留原內容：${targetName}。請選另一個輸出根目錄。`);
    const previous = JSON.parse(await previousFile.read());
    if (previous.schema !== 'psd-export-manifest@1' || previous.documentName !== documentName || !Array.isArray(previous.files) || previous.files.some(path => typeof path !== 'string')) throw new Error('舊產物清單無效，已保留原內容。');
    if (!previous.sourceId || previous.sourceId !== sourceId) throw new Error(`同名輸出屬於不同或無法辨識的來源 PSD：${targetName}。舊輸出已保留，請選另一個輸出根目錄或更改 PSD 名稱。`);
    return { existing, previous };
}

async function beginExport(root, title, sourceId, nonce = `${Date.now()}_${Math.floor(Math.random() * 1000000)}`) {
    if (typeof sourceId !== 'string' || !sourceId.trim()) throw new Error('缺少來源 PSD 識別，已取消匯出。');
    const documentName = safeDocumentName(title);
    const targetName = documentName + '_Export';
    const stageName = `_psd_stage_${documentName}_${nonce}`;
    const backupName = `_psd_backup_${documentName}_${nonce}`;
    await previousManifest(root, targetName, documentName, sourceId);
    if (await child(root, stageName) || await child(root, backupName)) throw new Error('匯出工作識別重複，請重試。');
    const stage = await root.createFolder(stageName);
    const journal = await stage.createFile(JOURNAL, { overwrite: false });
    await journal.write(JSON.stringify({ schema: 'psd-export-transaction@1', sourceId, targetName, stageName, backupName, phase: 'staging' }, null, 2));
    return { root, stage, documentName, sourceId, targetName, stageName, backupName };
}

async function preserveUserFiles(oldFolder, newFolder, owned, prefix = '') {
    for (const oldEntry of await oldFolder.getEntries()) {
        const path = prefix + oldEntry.name;
        if (path === MANIFEST || path === JOURNAL) continue;
        const replacement = await child(newFolder, oldEntry.name);
        if (oldEntry.isFolder) {
            if (replacement && !replacement.isFolder) throw new Error(`自訂資料夾與新檔案衝突：${path}`);
            const next = replacement || await newFolder.createFolder(oldEntry.name);
            await preserveUserFiles(oldEntry, next, owned, path + '/');
        } else if (!owned.has(path.toLowerCase())) {
            if (replacement) throw new Error(`自訂檔案與新輸出衝突：${path}。舊輸出已保留，請先改名自訂檔。`);
            await oldEntry.copyTo(newFolder, { overwrite: false });
        }
    }
}

async function publishExport(tx, validate) {
    await validate(tx.stage);
    const generated = (await filesIn(tx.stage)).filter(path => path !== MANIFEST && path !== JOURNAL);
    if (!generated.length) throw new Error('沒有產物，已保留舊輸出。');
    // Check again immediately before publication; the target may change during rendering.
    const ownership = await previousManifest(tx.root, tx.targetName, tx.documentName, tx.sourceId);
    const existing = ownership && ownership.existing;
    if (ownership) {
        const { previous } = ownership;
        await preserveUserFiles(existing, tx.stage, new Set(previous.files.map(path => path.toLowerCase())));
    }
    const manifest = await tx.stage.createFile(MANIFEST, { overwrite: false });
    await manifest.write(JSON.stringify({ schema: 'psd-export-manifest@1', documentName: tx.documentName, sourceId: tx.sourceId, files: generated }, null, 2));
    const journal = await child(tx.stage, JOURNAL);
    await journal.write(JSON.stringify({ schema: 'psd-export-transaction@1', sourceId: tx.sourceId, targetName: tx.targetName, stageName: tx.stageName, backupName: tx.backupName, phase: 'ready' }, null, 2));
    let backedUp = false;
    try {
        if (existing) { await existing.moveTo(tx.root, { newName: tx.backupName, overwrite: false }); backedUp = true; }
        await tx.stage.moveTo(tx.root, { newName: tx.targetName, overwrite: false });
    } catch (error) {
        if (backedUp) {
            try {
                const backup = await child(tx.root, tx.backupName);
                if (!backup) throw new Error('找不到備份資料夾');
                await backup.moveTo(tx.root, { newName: tx.targetName, overwrite: false });
            }
            catch (restoreError) { throw new Error(`發布失敗且自動還原未完成：${error.message}。完整舊版仍在 ${tx.backupName}；${restoreError.message}`); }
        }
        throw new Error(`發布失敗，舊版已保留：${error.message}；暫存：${tx.stageName}`);
    }
    return { folder: await child(tx.root, tx.targetName), backupName: backedUp ? tx.backupName : null, generatedFiles: generated.length };
}

module.exports = { beginExport, publishExport, safeDocumentName, documentSourceId, filesIn };
