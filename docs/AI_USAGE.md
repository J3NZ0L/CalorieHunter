# AI usage documentation

The chosen development phases were the proposed ones:
- design,
- implementation,
- and testing.

The detailed usage regarding the chosen three decision cases in the specific phases can be read below.

## Design

### Decision case 1

#### The problem
The problem that I choose from this phase, is the problem of how to make non-deterministic LLM outputs and date boundaries (like "today" vs "yesterday") completely determninistic in the unit tests.

#### Solution
The model I interacted with, proposed utilizing dependency injection overrides in the tests, while using working production LLM and time providers in production - specifically, the FastAPI Depends() function, by defining get_provider() and get_clock() methods and test overrides.

#### Verdict and reasoning
I accepted this proposal, because I knew this functionality available in FastAPI, and have already used it in the past, so I was familiar with the approach of dependency injection, and this exact implementation as well. In short, I think it is the technologically correct approach, because it does not require modifying runtime state untraceably via reaching into a module and overriding the result of a core function manually, rather, it involves defining a clearly distinctive method that will be used instead of the production equivalents at test time. I also briefly investigated alternative approaches, like the well-known "monkeypatching" approach in dynamic programming languages like python, where I would "manually" override a function or attribute at runtime. This latter approach would introduce clear code-maintainability issues and it is also hard to use when the type of object to override would be a built in C type.

For these reasons, I was happy to accept the proposed dependency injection override approach.

#### Tools used
- Claude Opus 5.5 via Claude Code CLI

#### Relevant context
- A draft of the [specification](/SPECIFICATION.md)

#### Verification Evidence :
- Code reference: Implemented in ... TODO
- Test reference: Utilized by tests in ... TODO
- Execution result: Running pytest ... TODO

## Implementation

### Tools used
- Google Antigravity CLI
    - Conductor plugin

### Relevant context
- Conductor plugin

## Testing

### Tools used

### Relevant context

