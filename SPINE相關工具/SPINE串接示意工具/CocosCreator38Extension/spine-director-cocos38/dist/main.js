'use strict';

const fs = require('fs');
const path = require('path');
const packageJSON = require('../package.json');
let lastHierarchyNodeUuids = [];

function safeToken(value, fallback) {
    const token = String(value || '')
        .normalize('NFKC')
        .replace(/[^\p{L}\p{N}_-]+/gu, '-')
        .replace(/^-+|-+$/g, '')
        .toLowerCase();
    return token || fallback;
}

function safeFileName(value, fallback) {
    const name = path.basename(String(value || fallback))
        .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
        .replace(/[. ]+$/g, '');
    return name || fallback;
}

function classToken(value) {
    const token = String(value || '')
        .normalize('NFKC')
        .replace(/[^\p{L}\p{N}_]+/gu, '_')
        .replace(/^_+|_+$/g, '');
    return token || 'Scene';
}

function decodeDataUrl(value) {
    if (typeof value !== 'string') {
        throw new Error('素材資料不是字串。');
    }
    const match = value.match(/^data:([^;,]+)?(?:;charset=[^;,]+)?;base64,(.*)$/s);
    if (!match) {
        throw new Error('素材不是有效的 Base64 data URL。');
    }
    return Buffer.from(match[2], 'base64');
}

function writeText(filePath, content) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, 'utf8');
}

function removeGeneratedFile(filePath) {
    const removed = [];
    for (const candidate of [filePath, `${filePath}.meta`]) {
        if (!fs.existsSync(candidate)) continue;
        fs.unlinkSync(candidate);
        removed.push(candidate);
    }
    return removed;
}

function writeBuffer(filePath, content) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
}

function normalizeFilePath(value) {
    if (!value || typeof value !== 'string') return '';
    if (value.startsWith('file://')) {
        try {
            return require('url').fileURLToPath(value);
        } catch (_) {
            return '';
        }
    }
    return value;
}

function findSourceByUuid(uuid) {
    if (!uuid) return '';
    const assetsRoot = path.join(Editor.Project.path, 'assets');
    const pending = [assetsRoot];

    while (pending.length) {
        const current = pending.pop();
        let entries;
        try {
            entries = fs.readdirSync(current, { withFileTypes: true });
        } catch (_) {
            continue;
        }

        for (const entry of entries) {
            const fullPath = path.join(current, entry.name);
            if (entry.isDirectory()) {
                pending.push(fullPath);
                continue;
            }
            if (!entry.isFile() || !entry.name.endsWith('.meta')) continue;

            try {
                const meta = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
                if (meta.uuid === uuid) return fullPath.slice(0, -'.meta'.length);
                const subMetas = meta.subMetas && typeof meta.subMetas === 'object'
                    ? Object.values(meta.subMetas)
                    : [];
                if (subMetas.some((subMeta) => subMeta && subMeta.uuid === uuid)) {
                    return fullPath.slice(0, -'.meta'.length);
                }
            } catch (_) {
                // Ignore invalid or concurrently generated meta files.
            }
        }
    }
    return '';
}

async function resolveSourceByUuid(uuid) {
    try {
        const info = await Editor.Message.request('asset-db', 'query-asset-info', uuid);
        const candidate = normalizeFilePath(info && (info.file || info.path));
        if (candidate && fs.existsSync(candidate)) return candidate;
    } catch (_) {
        // Some Creator 3.8 patch releases do not expose this message to extensions.
    }
    return findSourceByUuid(uuid);
}

function findFirstFile(root, extensions, recursive = false) {
    if (!root || !fs.existsSync(root)) return '';
    const entries = fs.readdirSync(root, { withFileTypes: true });
    for (const entry of entries) {
        if (!entry.isFile()) continue;
        const fullPath = path.join(root, entry.name);
        if (extensions.includes(path.extname(entry.name).toLowerCase())) return fullPath;
    }
    if (recursive) {
        for (const entry of entries) {
            if (!entry.isDirectory()) continue;
            const found = findFirstFile(path.join(root, entry.name), extensions, true);
            if (found) return found;
        }
    }
    return '';
}

function readSourceMeta(sourcePath) {
    const metaPath = `${sourcePath}.meta`;
    if (!fs.existsSync(metaPath)) return null;
    try {
        return JSON.parse(fs.readFileSync(metaPath, 'utf8'));
    } catch (_) {
        return null;
    }
}

function collectSpineCandidates(sourcePath) {
    if (!sourcePath || !fs.existsSync(sourcePath)) return [];
    if (!fs.statSync(sourcePath).isDirectory()) return [sourcePath];

    const results = [];
    const pending = [sourcePath];
    while (pending.length) {
        const current = pending.pop();
        let entries;
        try {
            entries = fs.readdirSync(current, { withFileTypes: true });
        } catch (_) {
            continue;
        }
        for (const entry of entries) {
            const fullPath = path.join(current, entry.name);
            if (entry.isDirectory()) {
                pending.push(fullPath);
                continue;
            }
            if (!entry.isFile()) continue;
            const extension = path.extname(entry.name).toLowerCase();
            if (extension !== '.skel' && extension !== '.json') continue;
            const meta = readSourceMeta(fullPath);
            if (meta && meta.importer === 'spine-data') results.push(fullPath);
        }
    }
    return results.sort((a, b) => a.localeCompare(b));
}

function findSkeletonByAtlasUuid(atlasUuid) {
    if (!atlasUuid) return '';
    const assetsRoot = path.join(Editor.Project.path, 'assets');
    const pending = [assetsRoot];

    while (pending.length) {
        const current = pending.pop();
        let entries;
        try {
            entries = fs.readdirSync(current, { withFileTypes: true });
        } catch (_) {
            continue;
        }

        for (const entry of entries) {
            const fullPath = path.join(current, entry.name);
            if (entry.isDirectory()) {
                pending.push(fullPath);
                continue;
            }
            if (!entry.isFile() || !entry.name.endsWith('.meta')) continue;
            try {
                const meta = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
                if (
                    meta.importer === 'spine-data' &&
                    meta.userData &&
                    meta.userData.atlasUuid === atlasUuid
                ) {
                    return fullPath.slice(0, -'.meta'.length);
                }
            } catch (_) {
                // Ignore invalid or concurrently generated meta files.
            }
        }
    }
    return '';
}

function atlasFromSkeletonMeta(skeletonPath) {
    const meta = readSourceMeta(skeletonPath);
    const atlasUuid = meta && meta.userData && meta.userData.atlasUuid;
    if (!atlasUuid) return '';
    const atlasPath = findSourceByUuid(atlasUuid);
    return atlasPath && path.extname(atlasPath).toLowerCase() === '.atlas' ? atlasPath : '';
}

function resolveSpineFiles(sourcePath) {
    if (!sourcePath) throw new Error('找不到 Cocos 選取資源的來源檔案。');

    let candidate = sourcePath;
    if (fs.statSync(candidate).isDirectory()) {
        candidate = findFirstFile(candidate, ['.skel', '.json'], true);
    }
    if (!candidate) throw new Error('選取資料夾內找不到 Spine .skel/.json。');

    const extension = path.extname(candidate).toLowerCase();
    const directory = path.dirname(candidate);
    const baseName = path.basename(candidate, extension);
    let skeletonPath = '';
    let atlasPath = '';

    if (extension === '.skel' || extension === '.json') {
        skeletonPath = candidate;
        const exactAtlas = path.join(directory, `${baseName}.atlas`);
        atlasPath = atlasFromSkeletonMeta(skeletonPath)
            || (fs.existsSync(exactAtlas) ? exactAtlas : findFirstFile(directory, ['.atlas']));
    } else if (extension === '.atlas') {
        atlasPath = candidate;
        const atlasMeta = readSourceMeta(atlasPath);
        skeletonPath = findSkeletonByAtlasUuid(atlasMeta && atlasMeta.uuid);
        const exactSkel = path.join(directory, `${baseName}.skel`);
        const exactJson = path.join(directory, `${baseName}.json`);
        if (!skeletonPath) {
            skeletonPath = fs.existsSync(exactSkel)
                ? exactSkel
                : (fs.existsSync(exactJson) ? exactJson : findFirstFile(directory, ['.skel', '.json']));
        }
    } else {
        const exactSkel = path.join(directory, `${baseName}.skel`);
        const exactJson = path.join(directory, `${baseName}.json`);
        skeletonPath = fs.existsSync(exactSkel)
            ? exactSkel
            : (fs.existsSync(exactJson) ? exactJson : findFirstFile(directory, ['.skel', '.json']));
        const exactAtlas = path.join(directory, `${baseName}.atlas`);
        atlasPath = skeletonPath ? atlasFromSkeletonMeta(skeletonPath) : '';
        if (!atlasPath) atlasPath = fs.existsSync(exactAtlas) ? exactAtlas : findFirstFile(directory, ['.atlas']);
    }

    if (!skeletonPath) throw new Error('找不到與選取資源配對的 .skel/.json。');
    if (!atlasPath) throw new Error('找不到與選取資源配對的 .atlas。');
    return { skeletonPath, atlasPath, baseName: path.basename(skeletonPath, path.extname(skeletonPath)) };
}

function imageMime(filePath) {
    switch (path.extname(filePath).toLowerCase()) {
        case '.jpg':
        case '.jpeg': return 'image/jpeg';
        case '.webp': return 'image/webp';
        default: return 'image/png';
    }
}

function toDataUrl(filePath) {
    return `data:${imageMime(filePath)};base64,${fs.readFileSync(filePath).toString('base64')}`;
}

function collectAtlasImages(atlasPath, atlasText) {
    const directory = path.dirname(atlasPath);
    const images = {};
    const lines = String(atlasText || '').split(/\r?\n/);

    for (const rawLine of lines) {
        const atlasName = rawLine.trim();
        if (!atlasName || atlasName.includes(':')) continue;
        const extension = path.extname(atlasName).toLowerCase();
        if (!['.png', '.jpg', '.jpeg', '.webp'].includes(extension)) continue;
        const imagePath = path.resolve(directory, atlasName);
        if (fs.existsSync(imagePath) && fs.statSync(imagePath).isFile()) {
            images[atlasName.replace(/\\/g, '/')] = toDataUrl(imagePath);
        }
    }

    if (!Object.keys(images).length) {
        for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
            if (!entry.isFile()) continue;
            if (!['.png', '.jpg', '.jpeg', '.webp'].includes(path.extname(entry.name).toLowerCase())) continue;
            images[entry.name] = toDataUrl(path.join(directory, entry.name));
        }
    }
    if (!Object.keys(images).length) throw new Error('Atlas 所在資料夾找不到貼圖檔。');
    return images;
}

function buildSpineBundle(files) {
    const atlasText = fs.readFileSync(files.atlasPath, 'utf8');
    const skeletonExtension = path.extname(files.skeletonPath).toLowerCase();
    const isBinary = skeletonExtension === '.skel';
    const relativePath = path.relative(path.join(Editor.Project.path, 'assets'), files.skeletonPath).replace(/\\/g, '/');
    const assets = {
        atlas: atlasText,
        images: collectAtlasImages(files.atlasPath, atlasText),
        skeleton: null,
        binarySkeleton: null
    };

    if (isBinary) {
        assets.binarySkeleton = `data:application/octet-stream;base64,${fs.readFileSync(files.skeletonPath).toString('base64')}`;
    } else {
        assets.skeleton = JSON.parse(fs.readFileSync(files.skeletonPath, 'utf8'));
    }

    return {
        name: files.baseName,
        sourceUrl: `db://assets/${relativePath}`,
        isBinary,
        assets
    };
}

async function executeSceneMethod(method, args = []) {
    return Editor.Message.request('scene', 'execute-scene-script', {
        name: packageJSON.name,
        method,
        args
    });
}

async function importCocosSpine(mode) {
    if (mode === 'node') {
        const nodeUuids = Editor.Selection.getSelected('node') || [];
        if (!nodeUuids.length) throw new Error('請先在「階層管理器」選取含有 sp.Skeleton 的節點。');
        const binding = await executeSceneMethod('inspectSelectedSpine', [nodeUuids]);
        if (!binding || !binding.assetUuid) {
            throw new Error('選取節點及其子節點找不到 sp.Skeleton 或 SkeletonData。');
        }
        const sourcePath = await resolveSourceByUuid(binding.assetUuid);
        const files = resolveSpineFiles(sourcePath);
        const item = {
            assetUuid: binding.assetUuid,
            bundle: buildSpineBundle(files),
            binding
        };
        return { ok: true, count: 1, items: [item], errors: [] };
    }

    const assetUuids = Editor.Selection.getSelected('asset') || [];
    if (!assetUuids.length) {
        throw new Error('請先在「資源管理器」選取 Spine 資源、複選多個資源，或選取包含 Spine 的資料夾。');
    }

    const errors = [];
    const filesBySkeleton = new Map();
    for (const selectedUuid of assetUuids) {
        const sourcePath = await resolveSourceByUuid(selectedUuid);
        if (!sourcePath) {
            errors.push(`找不到選取資源 UUID：${selectedUuid}`);
            continue;
        }
        const candidates = collectSpineCandidates(sourcePath);
        if (!candidates.length) {
            errors.push(`${sourcePath} 內找不到 Cocos Spine 資源`);
            continue;
        }
        for (const candidate of candidates) {
            try {
                const files = resolveSpineFiles(candidate);
                filesBySkeleton.set(files.skeletonPath.toLowerCase(), files);
            } catch (error) {
                errors.push(`${candidate}：${error && error.message ? error.message : error}`);
            }
        }
    }

    const allFiles = [...filesBySkeleton.values()];
    if (!allFiles.length) {
        throw new Error(errors.join('\n') || '選取內容找不到可匯入的 Spine。');
    }

    const items = [];
    for (let index = 0; index < allFiles.length; index += 1) {
        const files = allFiles[index];
        try {
            const bundle = buildSpineBundle(files);
            const skeletonMeta = readSourceMeta(files.skeletonPath);
            const assetUuid = skeletonMeta && skeletonMeta.uuid;
            if (!assetUuid) throw new Error('SkeletonData 的 .meta 缺少 UUID。');
            const previewX = (index - (allFiles.length - 1) / 2) * 220;
            const binding = await executeSceneMethod('ensurePreviewNode', [{
                assetUuid,
                name: bundle.name,
                position: { x: previewX, y: 0 }
            }]);
            items.push({ assetUuid, bundle, binding });
        } catch (error) {
            errors.push(`${files.skeletonPath}：${error && error.message ? error.message : error}`);
        }
    }
    if (!items.length) throw new Error(errors.join('\n') || 'Spine 批次匯入失敗。');

    return {
        ok: true,
        count: items.length,
        items,
        errors
    };
}

function rewriteAtlasImageNames(atlasText, imageNameMap) {
    return String(atlasText || '').split(/\r?\n/).map((line) => {
        const trimmed = line.trim();
        const replacement = imageNameMap.get(trimmed) || imageNameMap.get(path.basename(trimmed));
        return replacement ? line.replace(trimmed, replacement) : line;
    }).join('\n');
}

function buildEntrySource(className, configPath) {
    return `import { _decorator } from 'cc';
import { SpineDirectorPlayer } from './runtime/SpineDirectorPlayer';

const { ccclass } = _decorator;

@ccclass('${className}')
export class ${className} extends SpineDirectorPlayer {
    protected getDefaultConfigPath(): string {
        return '${configPath}';
    }
}
`;
}

function buildNativeTimelineEntrySource(className, configPath, runtimeImport = './runtime/CocosTimelinePlayer') {
    return `import { _decorator } from 'cc';
import { CocosTimelinePlayer } from '${runtimeImport}';

const { ccclass } = _decorator;

@ccclass('${className}')
export class ${className} extends CocosTimelinePlayer {
    protected getDefaultConfigPath(): string {
        return '${configPath}';
    }
}
`;
}

async function refreshAssets() {
    try {
        await Editor.Message.request('asset-db', 'refresh-asset', 'db://assets');
    } catch (error) {
        console.warn(`[${packageJSON.name}] Asset DB refresh failed; Creator should still detect the files.`, error);
    }
}

function validateNativeTimeline(project) {
    if (!project || project.schema !== 'cocos-native-timeline@1') {
        throw new Error('不是 Spine Director 的 Cocos Timeline 檔案。');
    }
    if (!Array.isArray(project.tracks)) {
        throw new Error('Timeline 缺少 tracks 資料。');
    }
    return project;
}

function collectDropTokens(input, output = new Set()) {
    if (Array.isArray(input)) {
        for (const item of input) collectDropTokens(item, output);
        return output;
    }
    if (input && typeof input === 'object') {
        for (const [key, value] of Object.entries(input)) {
            if (key === 'type' || key === 'types' || key === 'extends' || key === 'extens') continue;
            collectDropTokens(value, output);
        }
        return output;
    }
    if (typeof input !== 'string') return output;
    const value = input.trim();
    if (!value) return output;
    try {
        collectDropTokens(JSON.parse(value), output);
    } catch (_) {
        for (const token of value.match(/[A-Za-z0-9_+/-]{18,64}/g) || []) output.add(token);
    }
    return output;
}

function rememberHierarchySelection(type, value) {
    if (type !== 'node') return;
    const values = Array.isArray(value) ? value : [value];
    const uuids = values.filter((item) => typeof item === 'string' && item);
    if (uuids.length) lastHierarchyNodeUuids = uuids;
}

function collectHierarchySelectionCandidates() {
    const result = new Set();
    try {
        for (const uuid of Editor.Selection.getSelected('node') || []) {
            if (uuid) result.add(uuid);
        }
    } catch (_) {}
    try {
        const lastSelected = Editor.Selection.getLastSelected('node');
        if (lastSelected) result.add(lastSelected);
    } catch (_) {}
    if (result.size) return [...result];
    for (const uuid of lastHierarchyNodeUuids) {
        if (uuid) result.add(uuid);
    }
    return [...result];
}

function dumpValue(dump, fallback) {
    if (dump && typeof dump === 'object' && Object.prototype.hasOwnProperty.call(dump, 'value')) {
        return dump.value;
    }
    return dump === undefined || dump === null ? fallback : dump;
}

function dumpVector(dump, fallback) {
    const value = dumpValue(dump, fallback) || fallback;
    return {
        x: Number(dumpValue(value.x, fallback.x)) || 0,
        y: Number(dumpValue(value.y, fallback.y)) || 0,
        z: Number(dumpValue(value.z, fallback.z)) || 0
    };
}

function describeTimelineNodeDump(dump, fallbackUuid) {
    if (!dump) return null;
    const nodeUuid = String(dumpValue(dump.uuid, fallbackUuid) || fallbackUuid || '');
    if (!nodeUuid) return null;
    const position = dumpVector(dump.position, { x: 0, y: 0, z: 0 });
    const rotation = dumpVector(dump.rotation, { x: 0, y: 0, z: 0 });
    const scale = dumpVector(dump.scale, { x: 1, y: 1, z: 1 });
    const componentTypes = (dump.__comps__ || []).map((component) => (
        String(component && (component.cid || component.type || component.__type__ || component.name) || '')
    ));
    const hasType = (pattern) => componentTypes.some((type) => pattern.test(type));
    const opacityDump = (dump.__comps__ || []).find((component) => (
        /(^|\.)UIOpacity$/i.test(String(component && (component.cid || component.type || component.__type__) || ''))
    ));
    const opacity = opacityDump ? Number(dumpValue(opacityDump.opacity, 255)) : 255;
    return {
        nodeUuid,
        nodeName: String(dumpValue(dump.name, nodeUuid) || nodeUuid),
        transform: {
            x: position.x,
            y: position.y,
            z: position.z,
            rx: rotation.x,
            ry: rotation.y,
            rz: rotation.z,
            sx: scale.x || 1,
            sy: scale.y || 1,
            sz: scale.z || 1,
            active: dumpValue(dump.active, true) !== false,
            opacity: Number.isFinite(opacity) ? opacity : 255
        },
        capabilities: {
            spine: hasType(/(^|\.)(Skeleton)$/i) || hasType(/sp\.Skeleton/i),
            particle2d: hasType(/ParticleSystem2D/i),
            particle3d: hasType(/(^|\.)ParticleSystem$/i),
            animation: hasType(/(^|\.)Animation$/i),
            spineAnimations: [],
            animationClips: []
        }
    };
}

async function describeTimelineNodesRobust(nodeUuids) {
    const uuids = [...new Set((nodeUuids || []).filter((uuid) => typeof uuid === 'string' && uuid))];
    if (!uuids.length) return [];
    let sceneScriptError = null;
    try {
        const described = await executeSceneMethod('describeTimelineNodes', [uuids]);
        if (Array.isArray(described) && described.length) return described;
    } catch (error) {
        sceneScriptError = error;
    }
    const fallback = [];
    for (const uuid of uuids) {
        try {
            const dump = await Editor.Message.request('scene', 'query-node', uuid);
            const described = describeTimelineNodeDump(dump, uuid);
            if (described) fallback.push(described);
        } catch (_) {}
    }
    if (fallback.length) return fallback;
    if (sceneScriptError) throw sceneScriptError;
    return [];
}

exports.load = function load() {
    const selected = collectHierarchySelectionCandidates();
    if (selected.length) lastHierarchyNodeUuids = selected;
};
exports.unload = function unload() {};

exports.methods = {
    onSelectionSelect(type, value) {
        rememberHierarchySelection(type, value);
        if (type === 'node') {
            const selected = collectHierarchySelectionCandidates();
            if (selected.length) lastHierarchyNodeUuids = selected;
        }
    },

    onSelectionHover(type, value) {
        rememberHierarchySelection(type, value);
    },

    openPanel() {
        Editor.Panel.open(packageJSON.name);
    },

    async exportProject(payload) {
        if (!payload || payload.schema !== 'spine-director-cocos38@1') {
            throw new Error('不支援的輸出資料格式。');
        }
        if (payload.spineVersion !== '3.8') {
            throw new Error('Cocos Creator 3.8 版只接受 Spine 3.8 專案。');
        }
        if (!Array.isArray(payload.bundles) || !payload.config) {
            throw new Error('輸出資料缺少素材或播放設定。');
        }

        const projectSlug = safeToken(payload.projectName, 'spine-scene');
        const className = `SpineDirectorEntry_${classToken(projectSlug)}`;
        const projectPath = Editor.Project.path;
        const resourceRoot = path.join(projectPath, 'assets', 'resources', 'spine-director', projectSlug);
        const runtimeRoot = path.join(projectPath, 'assets', 'spine-director');
        const configPath = `spine-director/${projectSlug}/director`;

        fs.mkdirSync(resourceRoot, { recursive: true });

        for (const bundle of payload.bundles) {
            const bundleKey = safeToken(bundle.key, 'asset');
            const bundleDir = path.join(resourceRoot, bundleKey);
            fs.mkdirSync(bundleDir, { recursive: true });

            if (bundle.type === 'spine') {
                const baseName = safeFileName(bundle.baseName, bundleKey).replace(/\.(skel|json)$/i, '');
                const imageNameMap = new Map();
                const images = bundle.images && typeof bundle.images === 'object' ? bundle.images : {};

                for (const [originalName, dataUrl] of Object.entries(images)) {
                    const outputName = safeFileName(originalName, 'texture.png');
                    imageNameMap.set(originalName, outputName);
                    imageNameMap.set(path.basename(originalName), outputName);
                    writeBuffer(path.join(bundleDir, outputName), decodeDataUrl(dataUrl));
                }

                const atlasText = rewriteAtlasImageNames(bundle.atlas, imageNameMap);
                writeText(path.join(bundleDir, `${baseName}.atlas`), atlasText);

                if (bundle.binarySkeleton) {
                    writeBuffer(path.join(bundleDir, `${baseName}.skel`), decodeDataUrl(bundle.binarySkeleton));
                } else if (bundle.skeleton) {
                    writeText(path.join(bundleDir, `${baseName}.json`), JSON.stringify(bundle.skeleton));
                } else {
                    throw new Error(`Spine 素材 ${bundleKey} 缺少 .skel/.json。`);
                }
            } else if (bundle.type === 'image') {
                const fileName = safeFileName(bundle.fileName, `${bundleKey}.png`);
                writeBuffer(path.join(bundleDir, fileName), decodeDataUrl(bundle.texture));
            }
        }

        const finalConfig = {
            ...payload.config,
            schema: 'spine-director-runtime@1',
            projectName: payload.projectName,
            spineVersion: '3.8'
        };
        writeText(path.join(resourceRoot, 'director.json'), JSON.stringify(finalConfig, null, 2));

        const runtimeTemplate = path.join(__dirname, '..', 'static', 'runtime', 'SpineDirectorPlayer.ts');
        fs.mkdirSync(path.join(runtimeRoot, 'runtime'), { recursive: true });
        fs.copyFileSync(runtimeTemplate, path.join(runtimeRoot, 'runtime', 'SpineDirectorPlayer.ts'));
        writeText(path.join(runtimeRoot, `${className}.ts`), buildEntrySource(className, configPath));

        await refreshAssets();

        return {
            ok: true,
            projectSlug,
            className,
            configPath,
            assetUrl: `db://assets/resources/spine-director/${projectSlug}/director.json`,
            outputPath: resourceRoot
        };
    },

    async createPlayerNode(options) {
        if (!options || !options.className) {
            throw new Error('尚未輸出可用的播放器元件。');
        }
        return Editor.Message.request('scene', 'execute-scene-script', {
            name: packageJSON.name,
            method: 'createPlayerNode',
            args: [options]
        });
    },

    async importSelectedSpine() {
        return importCocosSpine('asset');
    },

    async bindSelectedSpineNode() {
        return importCocosSpine('node');
    },

    async previewScene(payload) {
        return executeSceneMethod('applyPreview', [payload]);
    },

    async restoreScenePreview() {
        return executeSceneMethod('restorePreview');
    },

    async timelineAddSelected() {
        const nodeUuids = collectHierarchySelectionCandidates();
        if (!nodeUuids.length) {
            throw new Error('請先在 Hierarchy 選取已放入 Scene 的物件。');
        }
        return describeTimelineNodesRobust(nodeUuids);
    },

    async timelinePeekSelection() {
        const nodeUuids = collectHierarchySelectionCandidates();
        if (!nodeUuids.length) return [];
        try {
            return await describeTimelineNodesRobust(nodeUuids);
        } catch (_) {
            return [];
        }
    },

    async timelineAddDropped(payload) {
        const candidates = [...collectDropTokens(payload)];
        if (candidates.length) {
            const described = await describeTimelineNodesRobust(candidates);
            if (described && described.length) return described;
        }
        const selected = collectHierarchySelectionCandidates();
        if (!selected.length) {
            const lastType = (() => {
                try { return Editor.Selection.getLastSelectedType() || 'none'; } catch (_) { return 'unknown'; }
            })();
            if (lastType === 'asset') {
                throw new Error('目前收到的是 Assets 素材，不是 Scene 節點。請先把素材放進 Scene，再從 Hierarchy 拖入該節點。');
            }
            throw new Error(`無法辨識拖曳資料，且沒有最近的 Hierarchy 節點（最後選取類型：${lastType}）。`);
        }
        return describeTimelineNodesRobust(selected);
    },

    async timelineInspectNodes(nodeUuids) {
        return describeTimelineNodesRobust(nodeUuids || []);
    },

    async timelinePreview(payload) {
        return executeSceneMethod('applyNativeTimeline', [payload]);
    },

    async timelineRestore() {
        return executeSceneMethod('restoreNativeTimeline');
    },

    async timelineSave(project) {
        validateNativeTimeline(project);
        const descriptions = await describeTimelineNodesRobust(
            project.tracks.map((track) => track.nodeUuid)
        );
        const descriptionsByUuid = new Map(
            descriptions.map((description) => [description.nodeUuid, description])
        );
        for (const track of project.tracks) {
            const description = descriptionsByUuid.get(track.nodeUuid);
            if (description && description.nodePath) track.nodePath = description.nodePath;
        }
        const fileName = `${safeFileName(project.name, 'MainTimeline')}.timeline.json`;
        const timelineName = safeFileName(project.name, 'MainTimeline');
        const timelineBaseRoot = path.join(
            Editor.Project.path,
            'assets',
            'Game',
            'Animation',
            'Timeline'
        );
        const timelineRoot = path.join(timelineBaseRoot, timelineName);
        const outputRoot = path.join(timelineRoot, 'resources');
        const outputPath = path.join(outputRoot, fileName);
        writeText(outputPath, JSON.stringify(project, null, 2));

        const runtimeRoot = timelineBaseRoot;
        const runtimeTemplate = path.join(
            __dirname,
            '..',
            'static',
            'runtime',
            'CocosTimelinePlayer.ts'
        );
        fs.mkdirSync(path.join(runtimeRoot, 'runtime'), { recursive: true });
        fs.copyFileSync(
            runtimeTemplate,
            path.join(runtimeRoot, 'runtime', 'CocosTimelinePlayer.ts')
        );
        const className = `TimelinePlayer_${classToken(project.name)}`;
        const resourceName = fileName.replace(/\.json$/i, '');
        const configPath = resourceName;
        const timelinePlayerPath = path.join(timelineRoot, `${className}.ts`);
        writeText(
            timelinePlayerPath,
            buildNativeTimelineEntrySource(className, configPath, '../runtime/CocosTimelinePlayer')
        );

        const legacyTimelinePath = path.join(
            Editor.Project.path,
            'assets',
            'resources',
            'SpineDirector',
            'Timelines',
            fileName
        );
        const legacyPlayerPath = path.join(
            Editor.Project.path,
            'assets',
            'SpineDirector',
            `${className}.ts`
        );
        const previousTimelinePath = path.join(
            timelineBaseRoot,
            'resources',
            fileName
        );
        const previousPlayerPath = path.join(
            timelineBaseRoot,
            `${className}.ts`
        );
        const migratedFiles = [
            ...removeGeneratedFile(legacyTimelinePath),
            ...removeGeneratedFile(legacyPlayerPath),
            ...removeGeneratedFile(previousTimelinePath),
            ...removeGeneratedFile(previousPlayerPath)
        ];

        await refreshAssets();
        return {
            ok: true,
            outputPath,
            playerPath: timelinePlayerPath,
            className,
            configPath,
            timelineName,
            timelineRoot,
            migratedFiles,
            assetUrl: `db://assets/Game/Animation/Timeline/${timelineName}/resources/${fileName}`
        };
    },

    async timelineLoadSelected() {
        const assetUuids = Editor.Selection.getSelected('asset') || [];
        if (assetUuids.length !== 1) {
            throw new Error('請先在 Assets 選取一個 .timeline.json 檔案。');
        }
        const sourcePath = await resolveSourceByUuid(assetUuids[0]);
        if (!sourcePath || !fs.existsSync(sourcePath)) {
            throw new Error('找不到選取的 Timeline 檔案。');
        }
        if (!sourcePath.toLowerCase().endsWith('.timeline.json')) {
            throw new Error('「開啟」只接受 .timeline.json；Spine 動畫請直接加入 Spine Animation 軌道。');
        }
        let project;
        try {
            project = validateNativeTimeline(JSON.parse(fs.readFileSync(sourcePath, 'utf8')));
        } catch (error) {
            throw new Error(`Timeline JSON 格式錯誤：${error.message || error}`);
        }
        const relativePath = path.relative(path.join(Editor.Project.path, 'assets'), sourcePath).replace(/\\/g, '/');
        return {
            ok: true,
            project,
            assetUrl: `db://assets/${relativePath}`
        };
    }
};
