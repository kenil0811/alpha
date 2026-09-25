# Fake-builder packages (F07)

`notes_ok` is a small, domain-neutral App with a screen that passes every candidate check. The
F07 integration tests copy it and introduce exactly one defect per variant (missing handler,
fake persistence, broken action, blocking overflow, a screen that fakes saving or hides errors,
undeclared or platform imports, dependency files, a wrong profile), so each defect sits next to
the test that expects it to be caught. The fake harness copies a package into the build
workspace (`fake:package <name> [<repair name> ...]`); it proves the pipeline, never generation.
