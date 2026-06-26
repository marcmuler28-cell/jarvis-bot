const path = require('path');
const electronInstaller = require('electron-winstaller');

async function main() {
  const appPath = path.join(__dirname, 'dist', 'JarvisBot-win32-x64');
  const outputPath = path.join(__dirname, 'dist', 'installer');

  console.log('Creating Windows installer from:', appPath);

  try {
    await electronInstaller.createWindowsInstaller({
      appDirectory: appPath,
      outputDirectory: outputPath,
      authors: 'JarvisBot',
      exe: 'JarvisBot.exe',
      setupExe: 'JarvisBot-Setup.exe',
      noMsi: true,
      skipUpdateIcon: true
    });
    console.log('Installer created at:', outputPath);
  } catch (error) {
    console.error('Error creating installer:', error);
    process.exit(1);
  }
}

main();
