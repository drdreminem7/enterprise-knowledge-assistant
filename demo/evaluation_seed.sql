INSERT INTO evaluation_sets (name, description)
VALUES (
  'HR and Policy Demo Set',
  'Small seed set for validating the enterprise knowledge assistant end to end.'
)
ON CONFLICT (name) DO NOTHING;

INSERT INTO evaluation_questions (set_id, question, expected_answer, document_scope)
SELECT
  evaluation_sets.id,
  seed.question,
  seed.expected_answer,
  seed.document_scope
FROM evaluation_sets
JOIN (
  VALUES
    (
      'How many remote work days are allowed per week?',
      'Employees may work remotely up to three days per week with manager approval.',
      'HR and policy demo documents'
    ),
    (
      'What is required for a reimbursement above 200 EUR?',
      'Manager approval is required for any single expense above 200 EUR.',
      'HR and policy demo documents'
    ),
    (
      'How quickly must security incidents be reported?',
      'Security incidents must be reported to the IT team within one hour of discovery.',
      'HR and policy demo documents'
    ),
    (
      'During which hours must employees remain reachable when working remotely?',
      'All employees must remain reachable during core working hours from 10:00 to 16:00.',
      'HR and policy demo documents'
    ),
    (
      'What devices may be used to access sensitive company data?',
      'Sensitive company data must only be accessed on approved devices with disk encryption enabled.',
      'HR and policy demo documents'
    ),
    (
      'How long do employees have to submit travel and meal expenses?',
      'Employees can submit travel and meal expenses within 30 days of purchase.',
      'HR and policy demo documents'
    ),
    (
      'What must every reimbursement include?',
      'All reimbursements require an itemized receipt.',
      'HR and policy demo documents'
    ),
    (
      'What password rule is required by the security policy?',
      'Passwords must be at least 12 characters long and should not be reused across services.',
      'HR and policy demo documents'
    ),
    (
      'Is multi-factor authentication required for company accounts?',
      'Multi-factor authentication is required for all company accounts.',
      'HR and policy demo documents'
    ),
    (
      'Who should security incidents be reported to?',
      'Security incidents must be reported to the IT team.',
      'HR and policy demo documents'
    )
) AS seed(question, expected_answer, document_scope)
ON true
WHERE evaluation_sets.name = 'HR and Policy Demo Set'
  AND NOT EXISTS (
    SELECT 1
    FROM evaluation_questions existing
    WHERE existing.set_id = evaluation_sets.id
      AND existing.question = seed.question
  );
