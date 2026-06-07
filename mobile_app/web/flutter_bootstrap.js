{{flutter_js}}
{{flutter_build_config}}

_flutter.loader.load({
  config: {
    renderer: "canvaskit"
  },
  onEntrypointLoaded: async function(engineInitializer) {
    const appRunner = await engineInitializer.initializeEngine();
    
    // Smoothly fade out and remove the custom splash screen loader
    const loader = document.getElementById('loading-indicator');
    if (loader) {
      loader.classList.add('fade-out');
      setTimeout(() => loader.remove(), 400); // 400ms matches the CSS transition duration
    }

    await appRunner.runApp();
  }
});
