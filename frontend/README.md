# Demo2Opt Frontend

This is a Vue 3 + Vite project for the Demo2Opt frontend.

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

Visit `http://localhost:8080` to see the application.

### Compile and Minify for Production

```sh
npm run build
```

The build artifacts will be in the `dist/` directory.

## Project Structure

- `src/`: Source code
  - `views/`: Page components (currently `Home.vue` contains the main dashboard)
  - `router/`: Vue Router configuration
  - `App.vue`: Root component
  - `main.js`: Entry point
- `public/`: Static assets
- `vite.config.js`: Vite configuration

## Notes

- The WebSocket connection port is configured in `src/views/Home.vue` (currently 8001).
- The frontend runs independently from the backend server during development.
