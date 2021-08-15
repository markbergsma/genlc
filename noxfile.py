# noxfile.py for genlc
import nox


@nox.session(python=["3.9", "3.8", "3.7"])
def tests(session):
    session.run("poetry", "install", external=True)
    session.run("pytest", "-m", "not e2e", "--cov")
