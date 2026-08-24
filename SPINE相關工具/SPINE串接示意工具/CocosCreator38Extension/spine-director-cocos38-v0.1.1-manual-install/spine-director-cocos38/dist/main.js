'use strict';

const fs = require('fs');
const path = require('path');
const packageJSON = require('../package.json');

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

function writeBuffer(filePath, content) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
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

async function refreshAssets() {
    try {
        await Editor.Message.request('asset-db', 'refresh-asset', 'db://assets');
    } catch (error) {
        console.warn(`[${packageJSON.name}] Asset DB refresh failed; Creator should still detect the files.`, error);
    }
}

exports.load = function load() {};
exports.unload = function unload() {};

exports.methods = {
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
    }
};
