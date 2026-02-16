from bs4 import BeautifulSoup

from app.utils.extractors.testpoint_extractor import extract_mcqs_testpoint
from app.models.mcqs_bank import AnswerOption


def test_testpoint_extract_handles_more_than_four_options_correct_in_extra():
    html = """
    <div id="content">
      <div>
        <h5><a class="theme-color" href="#">Which is a programming language?</a></h5>
        <ol type="A">
          <li>HTML</li>
          <li>CSS</li>
          <li>JSON</li>
          <li>XML</li>
          <li>SQL</li>
          <li class="correct">Python</li>
        </ol>
        <div class="question-explanation">Python is a programming language.</div>
      </div>
    </div>
    """

    soup = BeautifulSoup(html, "html.parser")
    mcqs = extract_mcqs_testpoint(soup)

    assert len(mcqs) == 1
    mcq = mcqs[0]

    # A-C preserved, D becomes Other
    assert mcq["option_a"] == "HTML"
    assert mcq["option_b"] == "CSS"
    assert mcq["option_c"] == "JSON"
    assert mcq["option_d"] == "Other"

    # Correct answer in extra options becomes OPTION_D (Other)
    assert mcq["correct_answer"] == AnswerOption.OPTION_D

    # Explanation includes additional options and correct answer marker
    assert mcq["explanation"]
    assert "Additional options:" in mcq["explanation"]
    assert "**Correct Answer:** Python" in mcq["explanation"]


def test_testpoint_extract_handles_more_than_four_options_correct_in_main():
    html = """
    <div id="content">
      <div>
        <h5><a class="theme-color" href="#">Capital of Pakistan?</a></h5>
        <ol type="A">
          <li>Karachi</li>
          <li>Lahore</li>
          <li class="correct">Islamabad</li>
          <li>Peshawar</li>
          <li>Quetta</li>
        </ol>
      </div>
    </div>
    """

    soup = BeautifulSoup(html, "html.parser")
    mcqs = extract_mcqs_testpoint(soup)

    assert len(mcqs) == 1
    mcq = mcqs[0]

    assert mcq["option_d"] == "Other"
    assert mcq["correct_answer"] == AnswerOption.OPTION_C
    assert "Additional options:" in (mcq["explanation"] or "")
