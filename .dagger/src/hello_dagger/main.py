import random
from typing import Annotated

import dagger
from dagger import DefaultPath, Doc, dag, function, object_type


@object_type
class HelloDagger:
    @function
    async def publish(
        self,
        source: Annotated[
            dagger.Directory, DefaultPath("/"), Doc("hello-dagger source directory")
        ],
    ) -> str:
        """Publish the application container after building and testing it on-the-fly"""
        await self.test(source)
        return await self.build(source).publish(
            f"ttl.sh/hello-dagger-{random.randrange(10**8)}"
        )

    @function
    def build(
        self,
        source: Annotated[
            dagger.Directory, DefaultPath("/"), Doc("hello-dagger source directory")
        ],
    ) -> dagger.Container:
        """Build the application container"""
        build = (
            self.build_env(source)
            .with_exec(["npm", "run", "build"])
            .directory("./dist")
        )
        return (
            dag.container()
            .from_("nginx:1.25-alpine")
            .with_directory("/usr/share/nginx/html", build)
            .with_exposed_port(80)
        )

    @function
    async def test(
        self,
        source: Annotated[
            dagger.Directory, DefaultPath("/"), Doc("hello-dagger source directory")
        ],
    ) -> str:
        """Return the result of running unit tests"""
        return await (
            self.build_env(source)
            .with_exec(["npm", "run", "test:unit", "run"])
            .stdout()
        )

    @function
    def build_env(
        self,
        source: Annotated[
            dagger.Directory, DefaultPath("/"), Doc("hello-dagger source directory")
        ],
    ) -> dagger.Container:
        """Build a ready-to-use development environment"""
        node_cache = dag.cache_volume("node")
        return (
            dag.container()
            .from_("node:21-slim")
            .with_directory("/src", source)
            .with_mounted_cache("/root/.npm", node_cache)
            .with_workdir("/src")
            .with_exec(["npm", "install"])
        )

    @function
    async def develop(
        self,
        assignment: Annotated[str, Doc("Assignment to complete")],
        source: Annotated[dagger.Directory, DefaultPath("/")],
    ) -> dagger.Directory:
        """A coding agent for developing new features."""
        # Environment with agent inputs and outputs
        environment = (
            dag.env()
            .with_string_input(
                "assignment", assignment, "the assignment to complete"
            )
            .with_workspace_input(
                "workspace",
                dag.workspace(source),
                "the workspace with tools to edit and test code",
            )
            .with_workspace_output(
                "completed", "the workspace with the completed assignment"
            )
        )
    
        # Detailed prompt stored in markdown file
        prompt_file = dag.current_module().source().file("develop_prompt.md")
    
        # Put it all together to form the agent
        work = dag.llm().with_env(environment).with_prompt_file(prompt_file)
    
        # Get the output from the agent
        completed = work.env().output("completed").as_workspace()
        completed_directory = completed.source().without_directory("node_modules")
    
        # Make sure the tests really pass
        await self.test(completed_directory)
    
        # Return the Directory with the assignment completed
        return completed_directory

    @function
    async def develop_issue(
        self,
        github_token: Annotated[
            dagger.Secret, Doc("Github Token with permissions to write issues and contents")
        ],
        issue_id: Annotated[int, Doc("Github issue number")],
        repository: Annotated[str, Doc("Github repository url")],
        source: Annotated[dagger.Directory, DefaultPath("/")],
    ) -> str:
        """Develop with a Github issue as the assignment and open a pull request."""
        # Get the Github issue
        issue_client = dag.github_issue(token=github_token)
        issue = issue_client.read(repository, issue_id)
    
        # Get information from the Github issue
        assignment = await issue.body()
    
        # Solve the issue with the Develop agent
        feature = await self.develop(assignment, source)
    
        # Open a pull request
        title = await issue.title()
        url = await issue.url()
        body = f"{assignment}\n\nCloses {url}"
        pr = issue_client.create_pull_request(repository, title, body, feature)
    
        return await pr.url()
