import fsPromises from 'fs/promises';
import { Dirent } from 'fs';
import path from 'path';
import micromatch from 'micromatch'; // For glob pattern matching
import { createContextLogger } from '../utils/logger.js';
import { FileSystemError } from '../utils/errors.js';
import config from '../config/index.js'; // Import config to access default ignore patterns
import { ModuleInfo, MultiModuleProjectStructure } from '../analyzer/types.js';

const logger = createContextLogger('FileScanner');

/**
 * Represents basic information about a scanned file.
 */
export interface FileInfo {
    /** Absolute path to the file. */
    path: string;
    /** File name. */
    name: string;
    /** File extension (including the dot). */
    extension: string;
    // Optional: Add size, modified time if needed later
    // size?: number;
    // modifiedTime?: Date;
}

/**
 * Extended file info with module awareness.
 */
export interface ModuleAwareFileInfo extends FileInfo {
    /** Module this file belongs to (null for root-level files) */
    moduleName: string | null;
    /** Relative path within the module */
    moduleRelativePath: string | null;
    /** Whether file is in src/main, src/test, or other */
    sourceType: 'main' | 'test' | 'resource' | 'other';
}

/**
 * Scans a directory recursively for files matching specified extensions,
 * respecting ignore patterns.
 */
export class FileScanner {
    private readonly targetDirectory: string;
    private readonly extensions: string[];

    private readonly combinedIgnorePatterns: string[]; // Store the final combined list

    /**
     * Creates an instance of FileScanner.
     * @param targetDirectory - The absolute path to the directory to scan.
     * @param extensions - An array of file extensions to include (e.g., ['.ts', '.js']).
     * @param ignorePatterns - An array of glob patterns to ignore.
     */
    constructor(targetDirectory: string, extensions: string[], userIgnorePatterns: string[] = []) {
        if (!path.isAbsolute(targetDirectory)) {
            throw new FileSystemError('FileScanner requires an absolute target directory path.');
        }
        this.targetDirectory = targetDirectory;
        this.extensions = extensions.map(ext => ext.startsWith('.') ? ext : `.${ext}`);

        // Combine default (from config) and user-provided ignore patterns
        let baseIgnorePatterns = [...config.ignorePatterns];

        // --- Fix: Prevent ignoring fixtures when scanning within __tests__ ---
        // This logic might be redundant now with the simplified isIgnored, but keep for clarity
        const isScanningFixtures = targetDirectory.includes('__tests__');
        if (isScanningFixtures) {
            // console.log('[FileScanner Diag] Scanning within __tests__, filtering out **/__tests__/** ignore pattern.'); // Removed log
            baseIgnorePatterns = baseIgnorePatterns.filter(pattern => pattern !== '**/__tests__/**');
        }
        // --- End Fix ---

        const combinedPatterns = new Set([...baseIgnorePatterns, ...userIgnorePatterns]);
        this.combinedIgnorePatterns = Array.from(combinedPatterns);

        logger.debug('FileScanner initialized', { targetDirectory, extensions: this.extensions, combinedIgnorePatterns: this.combinedIgnorePatterns });
        // console.log('[FileScanner Diag] Final Combined Ignore Patterns:', this.combinedIgnorePatterns); // Removed log
    }

    /**
     * Performs the recursive file scan.
     * @returns A promise that resolves to an array of FileInfo objects.
     * @throws {FileSystemError} If the target directory cannot be accessed.
     */
    async scan(): Promise<FileInfo[]> {
        logger.info(`Starting scan of directory: ${this.targetDirectory}`);
        const foundFiles: FileInfo[] = [];
        let scannedCount = 0;
        let errorCount = 0;

        try {
            await this.scanDirectoryRecursive(this.targetDirectory, foundFiles, (count) => scannedCount = count, (count) => errorCount = count);
            logger.info(`Scan completed: ${foundFiles.length} files matching criteria found. Scanned ${scannedCount} total items. Encountered ${errorCount} errors.`);
            return foundFiles;
        } catch (error: any) {
            logger.error(`Failed to scan directory: ${this.targetDirectory}`, { message: error.message });
            throw new FileSystemError(`Failed to scan directory: ${this.targetDirectory}`, { originalError: error });
        }
    }

    /**
     * Recursive helper function to scan directories.
     */
    private async scanDirectoryRecursive(
        currentPath: string,
        foundFiles: FileInfo[],
        updateScannedCount: (count: number) => void,
        updateErrorCount: (count: number) => void,
        currentScannedCount: number = 0,
        currentErrorCount: number = 0
    ): Promise<void> {
        // console.log(`[FileScanner Diag] Entering scanDirectoryRecursive for path: ${currentPath}`); // Removed log

        let localScannedCount = currentScannedCount;
        let localErrorCount = currentErrorCount;

        // --- Restore ignore checks ---
        // Check ignore patterns *before* reading directory
        if (this.isIgnored(currentPath)) {
            logger.debug(`Ignoring path (pre-check): ${currentPath}`); // Use logger.debug
            return;
        }
        // --- End restore ---


        let entries: Dirent[];
        try {
            entries = await fsPromises.readdir(currentPath, { withFileTypes: true });
             localScannedCount += entries.length; // Count items read in this directory
            updateScannedCount(localScannedCount);
        } catch (error: any) {
            logger.warn(`Cannot read directory, skipping: ${currentPath}`, { code: error.code });
            localErrorCount++;
            updateErrorCount(localErrorCount);
            return; // Skip this directory if unreadable
        }

        for (const entry of entries) {
            const entryPath = path.join(currentPath, entry.name);

            // --- Restore ignore checks ---
            // Check ignore patterns for each entry
            if (this.isIgnored(entryPath)) {
                logger.debug(`Ignoring path (entry check): ${entryPath}`); // Use logger.debug
                continue;
            }
            // --- End restore ---


            if (entry.isDirectory()) {
                await this.scanDirectoryRecursive(entryPath, foundFiles, updateScannedCount, updateErrorCount, localScannedCount, localErrorCount);
            } else if (entry.isFile()) {
                const extension = path.extname(entry.name).toLowerCase();
                // console.log(`[FileScanner Diag] Checking file: ${entryPath} with extension: ${extension}`); // Removed log
                if (this.extensions.includes(extension)) {
                    // console.log(`[FileScanner Diag] Found matching file: ${entryPath}`); // Removed log
                    foundFiles.push({
                        path: entryPath.replace(/\\/g, '/'), // Normalize path separators
                        name: entry.name,
                        extension: extension,
                    });
                }
            }
            // Ignore other entry types (symlinks, sockets, etc.) for now
        }
    }

    /**
     * Checks if a given path should be ignored based on configured patterns.
     * Uses micromatch for robust glob pattern matching.
     * @param filePath - Absolute path to check.
     * @returns True if the path should be ignored, false otherwise.
     */
    private isIgnored(filePath: string): boolean {
        // --- Restore original logic ---
        // Normalize path for consistent matching, especially on Windows
        const normalizedPath = filePath.replace(/\\/g, '/');
        // Use the combined list of ignore patterns (now potentially filtered in constructor)
        const isMatch = micromatch.isMatch(normalizedPath, this.combinedIgnorePatterns);
        // if (isMatch) { // Optional: Log when a path is ignored by patterns
        //     logger.debug(`Path ignored by pattern: ${filePath} (Normalized: ${normalizedPath})`);
        // }
        return isMatch;
        // --- End restore ---
    }

    /**
     * Enrich scanned files with module information.
     * @param files - The files to enrich
     * @param projectStructure - The parsed multi-module project structure
     * @returns Array of ModuleAwareFileInfo with module assignments
     */
    enrichWithModuleInfo(
        files: FileInfo[],
        projectStructure: MultiModuleProjectStructure | null
    ): ModuleAwareFileInfo[] {
        if (!projectStructure || projectStructure.modules.length === 0) {
            // No module structure - return files without module info
            return files.map(file => ({
                ...file,
                moduleName: null,
                moduleRelativePath: null,
                sourceType: this.determineSourceType(file.path, null),
            }));
        }

        logger.info(`Enriching ${files.length} files with module info from ${projectStructure.modules.length} modules`);

        // Sort modules by path length (longest first) for most specific matching
        const sortedModules = [...projectStructure.modules].sort(
            (a, b) => b.path.length - a.path.length
        );

        return files.map(file => {
            const moduleName = this.findModuleForFile(file.path, sortedModules, projectStructure.rootPath);
            const module = projectStructure.modules.find(m => m.name === moduleName);

            let moduleRelativePath: string | null = null;
            if (module && module.absolutePath) {
                moduleRelativePath = path.relative(module.absolutePath, file.path).replace(/\\/g, '/');
            }

            return {
                ...file,
                moduleName,
                moduleRelativePath,
                sourceType: this.determineSourceType(file.path, module || null),
            };
        });
    }

    /**
     * Find which module a file belongs to.
     */
    private findModuleForFile(
        filePath: string,
        sortedModules: ModuleInfo[],
        rootPath: string
    ): string | null {
        const normalizedFilePath = filePath.replace(/\\/g, '/');
        const normalizedRootPath = rootPath.replace(/\\/g, '/');

        // Get relative path from root
        const relativePath = path.relative(normalizedRootPath, normalizedFilePath).replace(/\\/g, '/');

        for (const module of sortedModules) {
            if (module.path === '.') continue; // Check non-root modules first

            const modulePath = module.path.replace(/\\/g, '/');

            // Check if file is under this module's directory
            if (relativePath.startsWith(modulePath + '/')) {
                return module.name;
            }
        }

        // Check if it's in the root module
        const rootModule = sortedModules.find(m => m.path === '.');
        if (rootModule) {
            // Verify it's not in any submodule
            const isInSubmodule = sortedModules.some(m => {
                if (m.path === '.') return false;
                const modulePath = m.path.replace(/\\/g, '/');
                return relativePath.startsWith(modulePath + '/');
            });

            if (!isInSubmodule) {
                return rootModule.name;
            }
        }

        return null;
    }

    /**
     * Determine the source type of a file.
     */
    private determineSourceType(
        filePath: string,
        module: ModuleInfo | null
    ): 'main' | 'test' | 'resource' | 'other' {
        const normalizedPath = filePath.replace(/\\/g, '/').toLowerCase();

        // Check for test directories
        if (normalizedPath.includes('/src/test/') ||
            normalizedPath.includes('/test/') ||
            normalizedPath.includes('/__tests__/') ||
            normalizedPath.includes('.test.') ||
            normalizedPath.includes('.spec.') ||
            normalizedPath.includes('-test/')) {
            return 'test';
        }

        // Check for resource directories
        if (normalizedPath.includes('/resources/') ||
            normalizedPath.includes('/assets/') ||
            normalizedPath.includes('/webapp/')) {
            return 'resource';
        }

        // Check for main source directories
        if (normalizedPath.includes('/src/main/') ||
            normalizedPath.includes('/src/') ||
            normalizedPath.includes('/main/')) {
            return 'main';
        }

        return 'other';
    }

    /**
     * Group files by module.
     */
    groupFilesByModule(files: ModuleAwareFileInfo[]): Map<string | null, ModuleAwareFileInfo[]> {
        const grouped = new Map<string | null, ModuleAwareFileInfo[]>();

        for (const file of files) {
            const moduleFiles = grouped.get(file.moduleName) || [];
            moduleFiles.push(file);
            grouped.set(file.moduleName, moduleFiles);
        }

        return grouped;
    }
}