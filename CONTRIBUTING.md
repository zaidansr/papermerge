# Contributing

Use Python 3.13 x64 with Tcl/Tk on Windows and follow the README setup instructions.

1. Read actual published public links; report source access errors instead of bypassing restrictions.
2. Keep network and PDF work off the Tk thread. Use worker queues and preserve cancellation.
3. Keep PDF saves atomic so failures cannot replace the destination.
4. Run `python -m unittest discover -s tests -v` and add meaningful tests for changed behaviour.
5. For packaging changes, run `build.ps1` and verify the packaged self-test.

Automated tests must run offline using synthetic fixtures or mocks. For manual repository checks, follow [TESTING.md](TESTING.md), record the date and exact filters, and keep network-dependent checks outside the offline test suite. Do not add exam PDFs, personal files, credentials, environments, or build output.

When updating the interface, keep README button labels and usage steps aligned with the actual app. Document source and published-release versions separately; a successful build does not publish a GitHub release.

Use focused commit messages such as `fix: preserve leading zeros in syllabus search`. Pull requests should explain the problem, resulting behaviour, and validation.

Contributions are provided under the project's MIT license.
