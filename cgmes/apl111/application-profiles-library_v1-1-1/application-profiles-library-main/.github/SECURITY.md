# Security policy
## Overview
The ENTSO-E Application Profiles Library repository does not contain executable software or external library dependencies. This eliminates risks typically associated with running or maintaining software, such as dependency vulnerabilities or executable file exploits. However, maintaining the integrity of the repository remains a priority.

## Reporting a vulnerability
If you identify any potential or confirmed security vulnerability in the ENTSO-E Application Profiles Libray repository, please report it privately to the CIM Working Group (WG) maintainers via email at [cim@entsoe.eu](mailto:cim@entsoe.eu)

In your email:
- Provide your name, company, and contact information.
- Include detailed steps to reproduce the issue and describe its potential impact.
To assess the severity of the vulnerability, you may refer to the [Apache severity rating scale](https://security.apache.org/blog/severityrating/) for guidance.

## Response time
- You will receive an acknowledgment of your report within 5 working days.
- If the issue is validated as a security vulnerability, the repository users will be informed, and appropriate action will be taken:
    - Critical and important vulnerabilities will be resolved within 30 calendar days.
    - Moderate or low-severity issues will be addressed in the next planned release.

## When to report a vulnerability
Please report vulnerabilities in the following scenarios:
- When you believe the ENTSO-E Application Profiles Libray repository may have been tampered with.
- When you suspect a security vulnerability but are unsure of its potential impact.

## ENTSO-E security requirements

### Threat model
The ENTSO-E Application Profiles Libray repository is designed to minimise security risks. Key considerations include:
1.	Known Vulnerabilities in Dependencies

    Not applicable: No external libraries or dependencies are used in this repository.
2.	Executable Code Risks

    Not applicable: No executable software is included in the repository.
3.	Repository Integrity

    The primary risk lies in unauthorized access to the GitHub repository, potentially leading to malicious changes. However, all changes must be validated and reviewed before being merged.
#### Non-Relevant Threats
1.	Infrastructure Risks

    Not applicable: The repository does not involve dedicated servers, databases, or executable operations.
2.	User Environment Risks

    Out of scope: Users are responsible for securing their own systems when using ENTSO-E-provided artifacts.
3.	Liability Disclaimer

    ENTSO-E provides the repository artifacts "as is" and, to the fullest extent permitted by law, is not liable for damages arising from their use.

## Implemented measures

To ensure repository integrity and security, ENTSO-E has implemented the following practices:

1.	Access Control

    Only authorized maintainers have writing access to the repository.

    Multi-factor authentication (MFA) is enforced for all maintainers.

2.	Change Validation

    All pull requests require at least one approval from a maintainer before merging.
3.	Audit Trails

    GitHub’s audit logs are reviewed periodically to monitor access and changes to the repository.
    Alerts are configured for unauthorized access attempts or suspicious activity.

4.	Community Engagement

    Users are encouraged to report any suspected vulnerabilities according to the guidelines in this document.

### Governance for Pull Requests

The ENTSO-E governance process ensures that repository integrity is maintained:
* Only maintainers may merge pull requests.
* Maintainers are experienced developers vetted by the ENTSO-E CIM Working Group.
* The approval process ensures that all changes are thoroughly reviewed for integrity and security before integration.
