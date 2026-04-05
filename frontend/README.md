# DabljaAR Frontend

The DabljaAR site frontend. built with React and Vite.

### File Structure
- `src/`: Contains the source code for the frontend application.
  - `components/`: Reusable React components.
  - `pages/`: Different pages of the application.
  - `assets/`: Static assets like images and styles.
  - `App.jsx`: Main application component.
  - `main.jsx`: Entry point for the React application.


### Getting Started

### Preferred (Ubuntu 22.04)

From the repository root, use the bootstrap script to prepare and run the stack:

```bash
./start.sh setup
./start.sh run
```

To work with frontend logs and lifecycle:

```bash
./start.sh logs frontend
./start.sh status
./start.sh stop
```

**Prerequisites**:
- Node.js (version 20 or later): Node 24.x is recommended.
- npm (comes with Node.js)

1. **Install Dependencies**:  
   Navigate to the `frontend` directory and run:
   ```bash
   npm install
   ```

2. **Run the Development Server**:  
   Start the development server with:
   ```bash
   npm run dev
   ```
   The application will be available at `http://localhost:5173` by default.

3. **Build for Production**:  
   To create a production build, run:
   ```bash
   npm run build
   ```
   The optimized files will be in the `dist` directory.

4. **Preview the Production Build**:  
   To preview the production build locally, run:
   ```bash
   npm run preview
   ```
    This will serve the files from the `dist` directory.

### Additional Scripts
- `npm run lint`: Lints the code using ESLint.
- `npm run format`: Formats the code using Prettier.
- `npm run test`: Runs the test suite (if tests are set up).

### Configuration
- **Vite Configuration**: The Vite configuration file is located at `vite.config.ts`.
- **Environment Variables**: You can create a `.env` file in the `frontend` directory to define environment-specific variables.

### License
This project is licensed under the MIT License. See the `LICENSE` file for details.