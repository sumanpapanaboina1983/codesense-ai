/**
 * Gradle Parser - Parses settings.gradle and build.gradle files
 * for multi-module project support.
 *
 * Supports:
 * - settings.gradle / settings.gradle.kts (module discovery)
 * - build.gradle / build.gradle.kts (dependencies, plugins)
 * - Groovy and Kotlin DSL syntax
 */

import * as fs from 'fs';
import * as path from 'path';
import { createContextLogger } from '../../utils/logger.js';
import {
    GradleSettingsParseResult,
    GradleBuildParseResult,
    GradlePluginInfo,
    GradleDependencyInfo,
    ProjectDependencyInfo,
    SourceSetInfo,
    DependencyExclusion,
    MultiModuleProjectStructure,
    ModuleInfo,
} from '../types.js';

const logger = createContextLogger('GradleParser');

/**
 * Parses Gradle project files to extract multi-module structure.
 */
export class GradleParser {
    private rootPath: string;
    private repositoryId: string;

    constructor(rootPath: string, repositoryId: string) {
        this.rootPath = rootPath;
        this.repositoryId = repositoryId;
    }

    /**
     * Parse the entire Gradle project structure.
     */
    async parseProject(): Promise<MultiModuleProjectStructure | null> {
        logger.info(`Parsing Gradle project at: ${this.rootPath}`);

        // Find settings file
        const settingsFile = this.findSettingsFile();
        if (!settingsFile) {
            logger.info('No settings.gradle found - treating as single-module project');
            return this.parseSingleModuleProject();
        }

        // Parse settings.gradle
        const settingsResult = await this.parseSettingsFile(settingsFile);
        if (!settingsResult) {
            logger.warn('Failed to parse settings.gradle');
            return null;
        }

        logger.info(`Found ${settingsResult.includedModules.length} modules in settings.gradle`);

        // Parse each module's build.gradle
        const modules: ModuleInfo[] = [];
        const moduleDependencyGraph = new Map<string, string[]>();

        for (const modulePath of settingsResult.includedModules) {
            const moduleInfo = await this.parseModule(modulePath);
            if (moduleInfo) {
                modules.push(moduleInfo);
                moduleDependencyGraph.set(moduleInfo.name, moduleInfo.moduleDependencies);
            }
        }

        // Also check for root build.gradle (common in multi-module projects)
        const rootBuildFile = this.findBuildFile(this.rootPath);
        if (rootBuildFile) {
            const rootModule: ModuleInfo = {
                name: settingsResult.rootProjectName || 'root',
                path: '.',
                absolutePath: this.rootPath,
                buildFilePath: rootBuildFile,
                moduleType: 'unknown',
                moduleDependencies: [],
            };

            const rootBuildResult = await this.parseBuildFile(rootBuildFile, '.');
            if (rootBuildResult) {
                rootModule.buildResult = rootBuildResult;
                rootModule.moduleDependencies = rootBuildResult.projectDependencies.map(d => d.moduleName);
            }

            // Insert root module at beginning
            modules.unshift(rootModule);
        }

        return {
            rootProjectName: settingsResult.rootProjectName,
            repositoryId: this.repositoryId,
            rootPath: this.rootPath,
            buildSystem: 'gradle',
            modules,
            moduleDependencyGraph,
        };
    }

    /**
     * Parse a single-module project (no settings.gradle).
     */
    private async parseSingleModuleProject(): Promise<MultiModuleProjectStructure | null> {
        const buildFile = this.findBuildFile(this.rootPath);
        if (!buildFile) {
            logger.info('No build.gradle found - not a Gradle project');
            return null;
        }

        const buildResult = await this.parseBuildFile(buildFile, '.');
        const projectName = path.basename(this.rootPath);

        const module: ModuleInfo = {
            name: projectName,
            path: '.',
            absolutePath: this.rootPath,
            buildFilePath: buildFile,
            buildResult: buildResult || undefined,
            moduleType: this.inferModuleType(buildResult?.plugins || []),
            moduleDependencies: buildResult?.projectDependencies.map(d => d.moduleName) || [],
        };

        return {
            rootProjectName: projectName,
            repositoryId: this.repositoryId,
            rootPath: this.rootPath,
            buildSystem: 'gradle',
            modules: [module],
            moduleDependencyGraph: new Map([[module.name, module.moduleDependencies]]),
        };
    }

    /**
     * Find the settings.gradle file.
     */
    private findSettingsFile(): string | null {
        const candidates = [
            'settings.gradle',
            'settings.gradle.kts',
        ];

        for (const candidate of candidates) {
            const filePath = path.join(this.rootPath, candidate);
            if (fs.existsSync(filePath)) {
                return filePath;
            }
        }

        return null;
    }

    /**
     * Find the build.gradle file in a directory.
     */
    private findBuildFile(dirPath: string): string | null {
        const candidates = [
            'build.gradle',
            'build.gradle.kts',
        ];

        for (const candidate of candidates) {
            const filePath = path.join(dirPath, candidate);
            if (fs.existsSync(filePath)) {
                return filePath;
            }
        }

        return null;
    }

    /**
     * Parse settings.gradle file.
     */
    async parseSettingsFile(filePath: string): Promise<GradleSettingsParseResult | null> {
        try {
            const content = fs.readFileSync(filePath, 'utf-8');
            const isKotlin = filePath.endsWith('.kts');

            const result: GradleSettingsParseResult = {
                rootProjectName: '',
                includedModules: [],
                pluginRepositories: [],
            };

            // Parse root project name
            const rootProjectMatch = isKotlin
                ? content.match(/rootProject\.name\s*=\s*"([^"]+)"/)
                : content.match(/rootProject\.name\s*=\s*['"]([^'"]+)['"]/);

            if (rootProjectMatch) {
                result.rootProjectName = rootProjectMatch[1];
            }

            // Parse include statements
            // Handles: include ':module1', ':module2'
            // Handles: include(':module1', ':module2')
            // Handles: include ':module1'
            // Handles: include(":module1")
            const includePatterns = [
                // Groovy: include ':module1', ':module2'
                /include\s+(['"]:[^'"]+['"]\s*(?:,\s*['"]:[^'"]+['"])*)/g,
                // Kotlin: include(":module1", ":module2")
                /include\s*\(\s*(["']:[^"']+["']\s*(?:,\s*["']:[^"']+["'])*)\s*\)/g,
            ];

            for (const pattern of includePatterns) {
                let match;
                while ((match = pattern.exec(content)) !== null) {
                    const modulesStr = match[1];
                    // Extract individual module names
                    const moduleMatches = modulesStr.match(/['"]:([\w\-:]+)['"]/g);
                    if (moduleMatches) {
                        for (const moduleMatch of moduleMatches) {
                            // Remove quotes and leading colon
                            const moduleName = moduleMatch.replace(/['"]/g, '').replace(/^:/, '');
                            if (moduleName && !result.includedModules.includes(moduleName)) {
                                result.includedModules.push(moduleName);
                            }
                        }
                    }
                }
            }

            // Also handle multiline includes
            const multilineIncludePattern = /include\s*\(\s*([\s\S]*?)\s*\)/g;
            let multiMatch;
            while ((multiMatch = multilineIncludePattern.exec(content)) !== null) {
                const innerContent = multiMatch[1];
                const moduleMatches = innerContent.match(/['"]:([\w\-:]+)['"]/g);
                if (moduleMatches) {
                    for (const moduleMatch of moduleMatches) {
                        const moduleName = moduleMatch.replace(/['"]/g, '').replace(/^:/, '');
                        if (moduleName && !result.includedModules.includes(moduleName)) {
                            result.includedModules.push(moduleName);
                        }
                    }
                }
            }

            logger.debug(`Parsed settings.gradle: rootProject=${result.rootProjectName}, modules=${result.includedModules.join(', ')}`);

            return result;
        } catch (error) {
            logger.error(`Failed to parse settings file: ${filePath}`, { error });
            return null;
        }
    }

    /**
     * Parse a single module.
     */
    async parseModule(modulePath: string): Promise<ModuleInfo | null> {
        // Convert Gradle module path (with colons) to file system path
        const fsPath = modulePath.replace(/:/g, '/');
        const absolutePath = path.join(this.rootPath, fsPath);

        if (!fs.existsSync(absolutePath)) {
            logger.warn(`Module directory not found: ${absolutePath}`);
            return null;
        }

        const buildFile = this.findBuildFile(absolutePath);
        if (!buildFile) {
            logger.warn(`No build.gradle found for module: ${modulePath}`);
            // Still create module info even without build file
            return {
                name: modulePath.replace(/:/g, '-').replace(/^-/, ''),
                path: fsPath,
                absolutePath,
                buildFilePath: '',
                moduleType: 'unknown',
                moduleDependencies: [],
            };
        }

        const buildResult = await this.parseBuildFile(buildFile, fsPath);

        return {
            name: modulePath.replace(/:/g, '-').replace(/^-/, ''),
            path: fsPath,
            absolutePath,
            buildFilePath: buildFile,
            buildResult: buildResult || undefined,
            moduleType: this.inferModuleType(buildResult?.plugins || []),
            moduleDependencies: buildResult?.projectDependencies.map(d => d.moduleName) || [],
        };
    }

    /**
     * Parse build.gradle file.
     */
    async parseBuildFile(filePath: string, modulePath: string): Promise<GradleBuildParseResult | null> {
        try {
            const content = fs.readFileSync(filePath, 'utf-8');
            const isKotlin = filePath.endsWith('.kts');

            const result: GradleBuildParseResult = {
                modulePath,
                plugins: [],
                dependencies: [],
                projectDependencies: [],
                extProperties: {},
                sourceSets: [],
                repositories: [],
            };

            // Parse plugins
            result.plugins = this.parsePlugins(content, isKotlin);

            // Parse dependencies
            const deps = this.parseDependencies(content, isKotlin);
            result.dependencies = deps.external;
            result.projectDependencies = deps.project;

            // Parse ext properties
            result.extProperties = this.parseExtProperties(content, isKotlin);

            // Parse group and version
            result.group = this.parseProperty(content, 'group', isKotlin);
            result.version = this.parseProperty(content, 'version', isKotlin);
            result.sourceCompatibility = this.parseProperty(content, 'sourceCompatibility', isKotlin);
            result.targetCompatibility = this.parseProperty(content, 'targetCompatibility', isKotlin);

            // Parse source sets
            result.sourceSets = this.parseSourceSets(content, isKotlin);

            // Parse repositories
            result.repositories = this.parseRepositories(content, isKotlin);

            logger.debug(`Parsed build.gradle for ${modulePath}: ${result.plugins.length} plugins, ${result.dependencies.length} external deps, ${result.projectDependencies.length} project deps`);

            return result;
        } catch (error) {
            logger.error(`Failed to parse build file: ${filePath}`, { error });
            return null;
        }
    }

    /**
     * Parse plugins from build.gradle.
     */
    private parsePlugins(content: string, isKotlin: boolean): GradlePluginInfo[] {
        const plugins: GradlePluginInfo[] = [];

        // Parse plugins {} block
        const pluginsBlockMatch = content.match(/plugins\s*\{([\s\S]*?)\n\}/);
        if (pluginsBlockMatch && pluginsBlockMatch[1]) {
            const pluginsBlock = pluginsBlockMatch[1];

            // id 'java' or id("java")
            const idPattern = isKotlin
                ? /id\s*\(\s*"([^"]+)"\s*\)(?:\s*version\s*\(\s*"([^"]+)"\s*\))?/g
                : /id\s+['"]([^'"]+)['"](?:\s+version\s+['"]([^'"]+)['"])?/g;

            let match;
            while ((match = idPattern.exec(pluginsBlock)) !== null) {
                if (match[1]) {
                    plugins.push({
                        id: match[1],
                        version: match[2],
                        appliedVia: 'plugins-block',
                    });
                }
            }

            // kotlin("jvm") syntax
            const kotlinPattern = /kotlin\s*\(\s*"([^"]+)"\s*\)/g;
            while ((match = kotlinPattern.exec(pluginsBlock)) !== null) {
                if (match[1]) {
                    plugins.push({
                        id: `org.jetbrains.kotlin.${match[1]}`,
                        appliedVia: 'plugins-block',
                    });
                }
            }

            // java or java-library without id()
            const simplePluginPattern = /^\s*(java|java-library|application|war|ear)\s*$/gm;
            while ((match = simplePluginPattern.exec(pluginsBlock)) !== null) {
                if (match[1]) {
                    plugins.push({
                        id: match[1],
                        appliedVia: 'plugins-block',
                    });
                }
            }
        }

        // Parse apply plugin: statements
        const applyPattern = /apply\s+plugin:\s*['"]([^'"]+)['"]/g;
        let match;
        while ((match = applyPattern.exec(content)) !== null) {
            if (match[1]) {
                plugins.push({
                    id: match[1],
                    appliedVia: 'apply-statement',
                });
            }
        }

        return plugins;
    }

    /**
     * Parse dependencies from build.gradle.
     */
    private parseDependencies(content: string, isKotlin: boolean): { external: GradleDependencyInfo[], project: ProjectDependencyInfo[] } {
        const external: GradleDependencyInfo[] = [];
        const project: ProjectDependencyInfo[] = [];

        // Find dependencies block
        const depsBlockMatch = content.match(/dependencies\s*\{([\s\S]*?)\n\}/);
        if (!depsBlockMatch || !depsBlockMatch[1]) {
            return { external, project };
        }

        const depsBlock = depsBlockMatch[1];

        // Parse project dependencies: implementation project(':module-name')
        const projectDepPatterns = [
            // implementation project(':module')
            /(\w+)\s+project\s*\(\s*['"]:([\w\-:]+)['"]\s*\)/g,
            // implementation(project(":module"))
            /(\w+)\s*\(\s*project\s*\(\s*['"]:([\w\-:]+)['"]\s*\)\s*\)/g,
        ];

        for (const pattern of projectDepPatterns) {
            let match;
            while ((match = pattern.exec(depsBlock)) !== null) {
                const configuration = match[1];
                const projectPath = match[2];
                if (configuration && projectPath) {
                    project.push({
                        configuration,
                        projectPath: `:${projectPath}`,
                        moduleName: projectPath.replace(/:/g, '-'),
                    });
                }
            }
        }

        // Parse external dependencies
        const externalDepPatterns = [
            // implementation 'group:artifact:version'
            /(\w+)\s+['"]([^:'"]+):([^:'"]+):([^'"]+)['"]/g,
            // implementation("group:artifact:version")
            /(\w+)\s*\(\s*["']([^:"']+):([^:"']+):([^"']+)["']\s*\)/g,
            // implementation group: 'x', name: 'y', version: 'z'
            /(\w+)\s+group:\s*['"]([^'"]+)['"]\s*,\s*name:\s*['"]([^'"]+)['"]\s*,\s*version:\s*['"]([^'"]+)['"]/g,
        ];

        for (const pattern of externalDepPatterns) {
            let match;
            while ((match = pattern.exec(depsBlock)) !== null) {
                const configuration = match[1];
                // Skip if this is a project dependency we already captured
                if (configuration === 'project' || !configuration || !match[2] || !match[3] || !match[4]) continue;

                external.push({
                    group: match[2],
                    artifact: match[3],
                    version: match[4],
                    configuration,
                    isProjectDependency: false,
                    isPlatform: configuration.includes('platform') || configuration === 'enforcedPlatform',
                });
            }
        }

        // Parse platform/BOM dependencies
        const platformPatterns = [
            /(\w+)\s+platform\s*\(\s*['"]([^:'"]+):([^:'"]+):([^'"]+)['"]\s*\)/g,
            /(\w+)\s*\(\s*platform\s*\(\s*["']([^:"']+):([^:"']+):([^"']+)["']\s*\)\s*\)/g,
        ];

        for (const pattern of platformPatterns) {
            let match;
            while ((match = pattern.exec(depsBlock)) !== null) {
                if (match[1] && match[2] && match[3] && match[4]) {
                    external.push({
                        group: match[2],
                        artifact: match[3],
                        version: match[4],
                        configuration: match[1],
                        isProjectDependency: false,
                        isPlatform: true,
                    });
                }
            }
        }

        return { external, project };
    }

    /**
     * Parse ext properties.
     */
    private parseExtProperties(content: string, isKotlin: boolean): Record<string, string> {
        const props: Record<string, string> = {};

        // ext { key = 'value' } or extra["key"] = "value"
        const extBlockMatch = content.match(/ext\s*\{([\s\S]*?)\n\}/);
        if (extBlockMatch && extBlockMatch[1]) {
            const extBlock = extBlockMatch[1];

            // key = 'value' or key = "value"
            const propPattern = /(\w+)\s*=\s*['"]([^'"]+)['"]/g;
            let match;
            while ((match = propPattern.exec(extBlock)) !== null) {
                if (match[1] && match[2]) {
                    props[match[1]] = match[2];
                }
            }
        }

        return props;
    }

    /**
     * Parse a simple property value.
     */
    private parseProperty(content: string, propName: string, isKotlin: boolean): string | undefined {
        const patterns = [
            new RegExp(`${propName}\\s*=\\s*['"]([^'"]+)['"]`),
            new RegExp(`${propName}\\s*=\\s*([\\w.]+)`),
        ];

        for (const pattern of patterns) {
            const match = content.match(pattern);
            if (match) {
                return match[1];
            }
        }

        return undefined;
    }

    /**
     * Parse source sets.
     */
    private parseSourceSets(content: string, isKotlin: boolean): SourceSetInfo[] {
        const sourceSets: SourceSetInfo[] = [];

        // Default Java source sets
        const defaultSets: SourceSetInfo[] = [
            { name: 'main', srcDirs: ['src/main/java', 'src/main/kotlin'], resourceDirs: ['src/main/resources'] },
            { name: 'test', srcDirs: ['src/test/java', 'src/test/kotlin'], resourceDirs: ['src/test/resources'] },
        ];

        // Check if custom source sets are defined
        const sourceSetBlockMatch = content.match(/sourceSets\s*\{([\s\S]*?)\n\}/);
        if (!sourceSetBlockMatch) {
            return defaultSets;
        }

        // For now, return defaults - parsing custom source sets is complex
        return defaultSets;
    }

    /**
     * Parse repositories.
     */
    private parseRepositories(content: string, isKotlin: boolean): string[] {
        const repos: string[] = [];

        const reposBlockMatch = content.match(/repositories\s*\{([\s\S]*?)\n\}/);
        if (reposBlockMatch && reposBlockMatch[1]) {
            const reposBlock = reposBlockMatch[1];

            // Common repository shortcuts
            if (/mavenCentral\s*\(\s*\)/.test(reposBlock)) repos.push('mavenCentral');
            if (/mavenLocal\s*\(\s*\)/.test(reposBlock)) repos.push('mavenLocal');
            if (/jcenter\s*\(\s*\)/.test(reposBlock)) repos.push('jcenter');
            if (/google\s*\(\s*\)/.test(reposBlock)) repos.push('google');

            // maven { url 'xxx' }
            const mavenUrlPattern = /maven\s*\{\s*url\s*[=:]?\s*['"]([^'"]+)['"]/g;
            let match;
            while ((match = mavenUrlPattern.exec(reposBlock)) !== null) {
                if (match[1]) {
                    repos.push(match[1]);
                }
            }
        }

        return repos;
    }

    /**
     * Infer module type from applied plugins.
     */
    private inferModuleType(plugins: GradlePluginInfo[]): ModuleInfo['moduleType'] {
        const pluginIds = plugins.map(p => p.id);

        if (pluginIds.includes('org.springframework.boot')) return 'spring-boot';
        if (pluginIds.includes('war')) return 'war';
        if (pluginIds.includes('ear')) return 'ear';
        if (pluginIds.includes('application')) return 'application';
        if (pluginIds.includes('java-library')) return 'java-library';
        if (pluginIds.includes('java')) return 'java-library';

        return 'unknown';
    }

    /**
     * Get the module a file belongs to based on its path.
     */
    getModuleForFile(filePath: string, modules: ModuleInfo[]): ModuleInfo | null {
        const relativePath = path.relative(this.rootPath, filePath);

        // Sort modules by path length (longest first) to match most specific module
        const sortedModules = [...modules].sort((a, b) => b.path.length - a.path.length);

        for (const module of sortedModules) {
            if (module.path === '.') continue; // Skip root module for now

            if (relativePath.startsWith(module.path + path.sep) || relativePath.startsWith(module.path + '/')) {
                return module;
            }
        }

        // Check if it's in root module
        const rootModule = modules.find(m => m.path === '.');
        if (rootModule) {
            // Check if it's not in any submodule
            const inSubmodule = modules.some(m =>
                m.path !== '.' &&
                (relativePath.startsWith(m.path + path.sep) || relativePath.startsWith(m.path + '/'))
            );
            if (!inSubmodule) {
                return rootModule;
            }
        }

        return null;
    }

    /**
     * Determine if a file is in main source, test source, or other.
     */
    getSourceType(filePath: string, module: ModuleInfo | null): 'main' | 'test' | 'resource' | 'other' {
        const relativePath = module
            ? path.relative(module.absolutePath, filePath)
            : path.relative(this.rootPath, filePath);

        if (relativePath.includes('src/main/java') || relativePath.includes('src/main/kotlin')) {
            return 'main';
        }
        if (relativePath.includes('src/test/java') || relativePath.includes('src/test/kotlin')) {
            return 'test';
        }
        if (relativePath.includes('src/main/resources') || relativePath.includes('src/test/resources')) {
            return 'resource';
        }
        if (relativePath.includes('/test/') || relativePath.includes('-test/')) {
            return 'test';
        }

        return 'other';
    }
}

/**
 * Quick check if a directory is a Gradle project.
 */
export function isGradleProject(rootPath: string): boolean {
    const indicators = [
        'settings.gradle',
        'settings.gradle.kts',
        'build.gradle',
        'build.gradle.kts',
        'gradlew',
        'gradlew.bat',
    ];

    return indicators.some(file => fs.existsSync(path.join(rootPath, file)));
}

/**
 * Quick check if a directory is a Maven project.
 */
export function isMavenProject(rootPath: string): boolean {
    return fs.existsSync(path.join(rootPath, 'pom.xml'));
}

/**
 * Detect the build system of a project.
 */
export function detectBuildSystem(rootPath: string): 'gradle' | 'maven' | 'unknown' {
    if (isGradleProject(rootPath)) return 'gradle';
    if (isMavenProject(rootPath)) return 'maven';
    return 'unknown';
}
