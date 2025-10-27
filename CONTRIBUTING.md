# Contributing to Kite WebSocket Python Client

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/socket.git
   cd socket
   ```
3. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

## Development Setup

### Install in Development Mode

```bash
pip install -e .
```

### Running Tests

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=kite_websocket --cov-report=html
```

Run specific test file:
```bash
pytest tests/test_client.py
```

### Code Quality

Before submitting a PR, ensure your code passes all checks:

**Format code with Black:**
```bash
black kite_websocket tests examples
```

**Lint with Flake8:**
```bash
flake8 kite_websocket
```

**Type check with MyPy:**
```bash
mypy kite_websocket
```

## Contribution Guidelines

### Code Style

- Follow PEP 8 guidelines
- Use Black for code formatting (line length: 100)
- Add type hints to all functions
- Write descriptive docstrings (Google style)

### Commit Messages

Use clear and descriptive commit messages:
- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Start with a capital letter
- Keep first line under 72 characters
- Reference issues and PRs when applicable

Examples:
```
Add support for order updates
Fix reconnection logic for edge cases
Update documentation for subscription modes
```

### Pull Request Process

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes:**
   - Write code
   - Add tests
   - Update documentation

3. **Test your changes:**
   ```bash
   pytest
   black kite_websocket tests
   flake8 kite_websocket
   ```

4. **Commit and push:**
   ```bash
   git add .
   git commit -m "Your descriptive commit message"
   git push origin feature/your-feature-name
   ```

5. **Create Pull Request:**
   - Go to GitHub and create a PR
   - Fill in the PR template
   - Link related issues
   - Wait for review

### What to Contribute

We welcome contributions in these areas:

- **Bug fixes**: Fix issues and edge cases
- **Features**: Add new functionality
- **Documentation**: Improve docs and examples
- **Tests**: Increase test coverage
- **Performance**: Optimize code
- **Examples**: Add usage examples

### Reporting Bugs

When reporting bugs, include:

1. **Description**: Clear description of the bug
2. **Steps to reproduce**: Minimal code to reproduce
3. **Expected behavior**: What should happen
4. **Actual behavior**: What actually happens
5. **Environment**:
   - Python version
   - OS and version
   - Package version
   - Dependencies versions

### Feature Requests

When requesting features:

1. **Use case**: Explain why this feature is needed
2. **Proposed solution**: Describe how it should work
3. **Alternatives**: Other solutions you've considered
4. **Examples**: Show example usage if possible

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Welcome newcomers
- Accept constructive criticism
- Focus on what's best for the community
- Show empathy towards others

### Unacceptable Behavior

- Harassment or discrimination
- Trolling or insulting comments
- Personal or political attacks
- Publishing others' private information
- Other unethical or unprofessional conduct

## Questions?

If you have questions, feel free to:
- Open an issue
- Start a discussion
- Contact the maintainers

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes
- GitHub contributors page

Thank you for contributing!
