# Contributing

Issues and pull requests are welcome.

Keep the project local-first. New agent wrappers should reset iTerm's background
when the child command exits, use a documented palette value, and pass through
unchanged outside iTerm2. New title detectors require a test for both the
positive transition and a nearby non-transition.

Run this before opening a pull request:

```zsh
make check
```

Do not include real terminal captures, personal paths, host names, credentials,
or agent transcripts in an issue, test, or documentation example.
