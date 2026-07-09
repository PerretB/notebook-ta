# Release Process

Releases are published by the GitHub Actions workflow in
`.github/workflows/release.yml`.

To publish to PyPI:

1. Ensure the release commit is on `main`.
2. Create and push a version tag that starts with `v`, for example `v0.1.0`.
3. The release workflow checks that the tag points to a commit reachable from `main`, builds a
   wheel, installs and tests it on the latest supported Python version, and uploads it to PyPI.

To test a release against TestPyPI, run the `Release` workflow manually with the same tag and set
`test_pypi` to `true`. For automatic tag-push releases, set the GitHub repository variable
`RELEASE_TEST_PYPI` to `true` before pushing the tag. Manual runs still require the tag to point to
a commit on `main`.

The workflow expects these GitHub repository secrets:

- `PYPI_API_TOKEN` for uploads to PyPI.
- `TEST_PYPI_API_TOKEN` for uploads to TestPyPI.
