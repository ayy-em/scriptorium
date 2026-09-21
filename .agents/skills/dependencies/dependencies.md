# Rules for working with third party dependencies

- Use context7 MCP for all external library documentation. 
- Never rely on training-data memory for library APIs. Call resolve-library-id then get-library-docs when referencing boto3, airflow, pandas, requests or any third-party package.
- Whenever you refer to dependency docs, make sure to check if the version defined in project's pyproject.toml is the latest one and notify the user in case it's not.
- Use uv to manage dependencies. Do not use pip, poetry, etc.
- `pyproject.toml` is the ultimate source of truth for dependency versions. It should always have the latest version of the dependency listed.
- When adding dependencies to `pyproject.toml`, bundle them in dependency groups.
