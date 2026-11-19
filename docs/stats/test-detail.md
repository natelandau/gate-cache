---
icon: lucide/list-checks
---

# Find slow and flaky tests

The dashboard shows which gates are slow or flaky. To see which tests make them slow or flaky, give gate-cache the test report that your test tool writes. The dashboard then names the slowest tests of each gate and the tests that fail only some of the time. You need [stats recording](record-stats.md) on.

## How it works

Most test tools can write a JUnit XML report: a file in a common XML format that lists each test with its result and its run time. The `--junit` option tells gate-cache where the command writes this report:

```sh
gate-cache --name unit --junit reports/unit.xml -- pytest --junitxml=reports/unit.xml
```

After the command runs, gate-cache reads the report and records the name, the result, and the run time of each test.

- gate-cache does not make the report. The command must write it, to the path that you give to `--junit`.
- `--junit` never changes whether a gate skips, the output of the command, or its exit code.
- If recording is off, gate-cache ignores `--junit` and prints nothing.
- A run that skips reads no report, because the command did not run.
- gate-cache reads only a report that the command wrote during this run. It ignores a report that an earlier run left behind.

To read more than one report, give `--junit` once for each path. A path can also be a folder. gate-cache then reads the `.xml` files directly in that folder. A relative path starts from the directory where you run gate-cache.

## Make your test tool write a report

Each tool has its own option for the report. Use the one for your tool, with the same path in `--junit`:

| Tool | Command | `--junit` path |
| --- | --- | --- |
| pytest (Python) | `pytest --junitxml=reports/unit.xml` | `reports/unit.xml` |
| Vitest (JavaScript) | `npx vitest run --reporter=junit --outputFile=reports/web.xml` | `reports/web.xml` |
| Jest (JavaScript) | `npx jest`, with the `jest-junit` package. Read [Set up Jest](#set-up-jest). | `reports/jest.xml` |
| Go, with gotestsum | `gotestsum --junitfile reports/go.xml` | `reports/go.xml` |
| PHPUnit (PHP) | `vendor/bin/phpunit --log-junit reports/php.xml` | `reports/php.xml` |
| Maven Surefire (Java) | `mvn test`, which writes the reports by default | `target/surefire-reports` |
| Gradle (Java, Kotlin) | `gradle test`, which writes the reports by default | `build/test-results/test` |

### Set up Jest

Jest needs the `jest-junit` package. Install it, then add it to the reporters in your Jest configuration:

```js title="jest.config.js"
module.exports = {
  reporters: [
    "default", // (1)!
    ["jest-junit", { outputDirectory: "reports", outputName: "jest.xml" }],
  ],
};
```

1.  Keep `default`, or Jest stops printing its usual output.

### Give a folder of reports

Maven Surefire and Gradle write one file for each test class, so give `--junit` the folder:

```sh
gate-cache --name java-test --junit target/surefire-reports -- mvn test
```

## Choose the report path

The path of the report decides whether gate-cache can record a pass, and whether the results of two gates stay apart.

- Put the report where git does not see it: a path that your `.gitignore` file lists, or a path outside the repository. A report file that git sees changes your files, so gate-cache cannot record the pass.
- Give each gate its own report path. If two runs write the same path at the same time, the results of one run can mix with the other.
- If the gate name has an `@` key, put the key in the path too. For example, give the gate `test@node20` the path `reports/test-node20.xml`. Then runs with different keys never write the same file.

For more about the key after the `@`, read [Write a gate](../guides/write-a-gate.md#cover-inputs-that-git-does-not-see).

## Read the results

Open the dashboard with `gate-cache dashboard`.

### Slowest tests

The details page of a gate lists its slowest tests. For each test, it shows:

- The median run time of the test, from its passing runs.
- That time as a share of the typical run time of the gate. A test with a large share is a good place to start to make the gate faster.
- The number of runs.

### Flaky tests

On the **Triage** page, each row with the **Flaky** reason lists the tests of its gate in two groups:

- **Flaky tests** both failed and passed with the same hash, that is, on identical files. Each one cost at least one failed run of the whole gate.
- **Passed on retry** lists tests that failed and then passed when the test tool ran them again in the same run. Only tools that run failed tests again write this into their report. The gate passed, but each retry added run time.

To find why a test is flaky, use the same patterns as for a flaky gate. Read [Fix a flaky gate](triage.md#fix-a-flaky-gate).

## Fix a report problem

If gate-cache could not use a report in recent runs of a gate, the details page of the gate shows a note. The note looks at the last 20 runs in the selected time range that ran the command, and counts each kind of problem. A run also counts when only some of its reports had a problem.

| Problem | Meaning | What to do |
| --- | --- | --- |
| missing | No file was at the path. | Make sure that the path in `--junit` is the same as the path that the test tool writes. A relative path starts from the directory where you run gate-cache. |
| stale | A file was at the path, but this run did not write it. | The test tool wrote its report somewhere else, or did not write one. Make sure that the command has the option that writes the report. A tool that skips tests when nothing changed, such as Gradle, also writes no new report. |
| unreadable | The file is not a JUnit XML report. | Make sure that the tool writes JUnit XML, and not another format. |

A run that stops before the test tool writes its report also counts as missing or stale.

## How long the history lasts

The dashboard keeps the results of each test for 90 days. It keeps the runs of each gate for 365 days. The numbers for tests cover only the last 90 days, even when you pick a longer time range.
