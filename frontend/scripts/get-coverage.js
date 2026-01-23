#!/usr/bin/env node

import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const coveragePath = join(__dirname, '../coverage/coverage-final.json');

try {
  const coverageData = JSON.parse(readFileSync(coveragePath, 'utf-8'));
  
  // Calculate overall coverage
  let totalStatements = 0;
  let coveredStatements = 0;
  let totalBranches = 0;
  let coveredBranches = 0;
  let totalFunctions = 0;
  let coveredFunctions = 0;
  let totalLines = 0;
  let coveredLines = 0;

  // Filter out test files and config files
  const excludePatterns = [
    /\.test\./,
    /\.spec\./,
    /test\//,
    /coverage\//,
    /node_modules\//,
    /\.config\./,
    /index\.js$/,
    /main\.jsx$/,
  ];

  for (const [file, data] of Object.entries(coverageData)) {
    // Skip excluded files
    if (excludePatterns.some(pattern => pattern.test(file))) {
      continue;
    }

    const s = data.s || {};
    const b = data.b || {};
    const f = data.f || {};
    const statementMap = data.statementMap || {};
    const branchMap = data.branchMap || {};
    const fnMap = data.fnMap || {};

    // Statements
    totalStatements += Object.keys(statementMap).length;
    coveredStatements += Object.values(s).filter(count => count > 0).length;

    // Branches
    totalBranches += Object.values(branchMap).reduce((sum, branch) => sum + (branch.locations?.length || 0), 0);
    coveredBranches += Object.values(b).reduce((sum, counts) => sum + counts.filter(c => c > 0).length, 0);

    // Functions
    totalFunctions += Object.keys(fnMap).length;
    coveredFunctions += Object.values(f).filter(count => count > 0).length;

    // Lines (approximate from statements)
    totalLines += Object.keys(statementMap).length;
    coveredLines += Object.values(s).filter(count => count > 0).length;
  }

  const statementsPercent = totalStatements > 0 ? (coveredStatements / totalStatements * 100).toFixed(2) : 0;
  const branchesPercent = totalBranches > 0 ? (coveredBranches / totalBranches * 100).toFixed(2) : 0;
  const functionsPercent = totalFunctions > 0 ? (coveredFunctions / totalFunctions * 100).toFixed(2) : 0;
  const linesPercent = totalLines > 0 ? (coveredLines / totalLines * 100).toFixed(2) : 0;

  console.log('\n📊 Code Coverage Summary\n');
  console.log(`Statements: ${statementsPercent}% (${coveredStatements}/${totalStatements})`);
  console.log(`Branches:   ${branchesPercent}% (${coveredBranches}/${totalBranches})`);
  console.log(`Functions:  ${functionsPercent}% (${coveredFunctions}/${totalFunctions})`);
  console.log(`Lines:      ${linesPercent}% (${coveredLines}/${totalLines})`);
  console.log(`\nOverall:    ${linesPercent}%`);
  
} catch (error) {
  console.error('Error reading coverage file:', error.message);
  console.error('Make sure to run "npm run test:coverage" first');
  process.exit(1);
}

