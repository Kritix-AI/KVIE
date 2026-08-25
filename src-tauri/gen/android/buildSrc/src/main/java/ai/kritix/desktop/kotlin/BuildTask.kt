import java.io.File
import org.apache.tools.ant.taskdefs.condition.Os
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.logging.LogLevel
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

open class BuildTask : DefaultTask() {
    @Input
    var rootDirRel: String? = null
    @Input
    var target: String? = null
    @Input
    var release: Boolean? = null

    @TaskAction
    fun assemble() {
        val baseExecutable = "npm"
        val executable = if (Os.isFamily(Os.FAMILY_WINDOWS)) "$baseExecutable.cmd" else baseExecutable
        
        try {
            runTauriCli(executable)
        } catch (e: Exception) {
            // If the process started but failed with a non-zero exit code, don't try fallbacks.
            // The error is likely in the Tauri CLI execution itself.
            if (isExecFailure(e)) {
                throw e
            }

            if (Os.isFamily(Os.FAMILY_WINDOWS)) {
                // Try different Windows-specific extensions if the first one wasn't found
                val fallbacks = listOf(
                    baseExecutable,
                    "$baseExecutable.exe",
                    "$baseExecutable.bat",
                )
                
                var lastException: Exception = e
                for (fallback in fallbacks) {
                    try {
                        runTauriCli(fallback)
                        return
                    } catch (fallbackException: Exception) {
                        if (isExecFailure(fallbackException)) {
                            throw fallbackException
                        }
                        lastException = fallbackException
                    }
                }
                throw lastException
            } else {
                throw e;
            }
        }
    }

    private fun isExecFailure(e: Exception): Boolean {
        val message = e.message ?: ""
        return message.contains("finished with non-zero exit value") || 
               e.javaClass.name.contains("ExecException")
    }

    fun runTauriCli(executable: String) {
        val rootDirRel = rootDirRel ?: throw GradleException("rootDirRel cannot be null")
        val target = target ?: throw GradleException("target cannot be null")
        val release = release ?: throw GradleException("release cannot be null")
        
        // Use 'android-studio-script' for IDE integration. 
        // Note: For debug builds, Tauri CLI may expect a running dev server.
        val args = mutableListOf("run", "tauri", "--", "android", "android-studio-script")

        project.exec {
            workingDir(File(project.projectDir, rootDirRel))
            executable(executable)
            
            if (project.logger.isEnabled(LogLevel.DEBUG)) {
                args.add("-vv")
            } else if (project.logger.isEnabled(LogLevel.INFO)) {
                args.add("-v")
            }
            
            if (release) {
                args.add("--release")
            }
            
            args.add("--target")
            args.add(target)
            
            args(args)
        }.assertNormalExitValue()
    }
}
