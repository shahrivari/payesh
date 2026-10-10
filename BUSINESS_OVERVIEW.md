# Payesh — Business Overview

## Executive Summary

Payesh provides a central workspace for monitoring announcements from Iran Fara Bourse (IFB) and Tehran Stock Exchange (
TSE). It collects recent announcements and their supporting documents, extracts available financial information, and
presents the results in a Persian dashboard.

The delivered application supports manual collection, scheduled updates, persistent storage, and access through a REST
API. It can run locally or be packaged as a Docker container. Its purpose is to reduce repetitive document retrieval and
make information easier to find and review.

## Business Need

Announcements are published across separate sources, with financial terms and interest schedules embedded in PDF and
Excel attachments. Reviewing these manually requires repeated source visits, downloads, and comparisons.

Payesh brings these steps into one workflow. Users can locate announcements, inspect available terms, review daily
interest amounts, and open the original documents when extraction needs human review.

## Delivered Capabilities

| Capability                                  | Business use                                                                                                  |
|---------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| Collection from IFB and TSE                 | Access both sources from one workspace.                                                                       |
| Persian interface with right-to-left layout | Review information in the language and layout used by the source documents.                                   |
| Search and filters                          | Find records by title, symbol, source, publication date, document type, or extraction status.                 |
| Structured financial information            | Review available rates, nominal values, maturity dates, and other supported terms without opening every file. |
| Daily interest tables                       | Inspect dated amounts extracted from supported documents and spreadsheets.                                    |
| Unified attachments section                 | See filenames, extraction status, and view/download links for supporting files.                               |
| Missing-field explanations                  | Understand which required fields were not extracted and which attachments need review.                        |
| Collection history                          | Review manual and scheduled runs, their outcomes, and reported failures.                                      |
| REST API                                    | Allow other applications to retrieve stored records, attachments, statistics, and collection results.         |

## Source Coverage and Selection Rules

### Iran Fara Bourse

Payesh collects the announcements in the current table returned by the IFB source and stores their available PDFs.
Structured extraction is limited to PDF filenames ending in `N.pdf`.

### Tehran Stock Exchange

Payesh checks only the newest announcement page, currently 20 announcements per update. A title qualifies when it
contains either:

- Both **پذیره** and **اوراق**; or
- Both **گشایش** and **اوراق**.

Persian and Arabic letter variations are normalized before matching. All PDF and Excel attachments on qualifying
announcements are eligible, regardless of filename. Images are excluded.

Neither source currently receives a full historical archive scan. Records already collected remain available for later
review.

## Information Collected and Extracted

### Announcement Information

For each collected announcement, Payesh retains the source, source identifier or notice number, title, publication date and time, and available trading symbol. TSE records also retain the available announcement summary. Attachment information includes the filename, file type, source download address, and download time.

The announcement publication date is separate from the issuance date of the securities described in its attachments.

### Financial Fields from Supporting Documents

The following fields are supported where the document contains recognizable information:

| Field | Business meaning |
| --- | --- |
| Document type (نوع سند) | Subscription, securities opening, daily interest, or an unrecognized document. |
| Instrument name and type (نام و نوع اوراق) | The securities described in the document. |
| Trading symbol and related symbols (نماد / نمادها) | The primary symbol and other identified symbols. |
| Issuer (ناشر) | The named issuer of the securities. |
| Market maker (بازارگردان) | The named market maker. |
| Guarantor (ضامن) | The named guarantor. |
| Profit formula (فرمول محاسبه سود) | Formula text identified in the document; Payesh does not evaluate it. |
| Annual profit or rental yield (نرخ سود سالانه) | The stated annual percentage rate. |
| Repurchase rate (نرخ بازخرید) | The stated repurchase percentage rate. |
| Nominal value (ارزش اسمی) | Face value per security, in rials. |
| Profit payment interval (فاصله پرداخت سود) | The interval between payments, in months. |
| Securities issuance date (تاریخ انتشار اوراق) | The date the securities are issued. |
| Maturity date (تاریخ سررسید) | The stated maturity date. |
| Subscription start and end (شروع / پایان پذیره‌نویسی) | Dates identified for the subscription window. |
| Subscription period (دوره پذیره‌نویسی) | The stated duration, such as a number of working days. |
| Securities term (مدت اوراق) | Duration in months and years; one unit may be converted from the other. |

PDF extraction supports these fields on a best-effort basis. Supported TSE Excel layouts additionally supply issuance and maturity dates, annual rate, nominal value, and payment interval when suitable labels and stored values are present. Document type for TSE announcements is determined from the title.

### Interest and Payment Tables

- **Daily interest rows:** a date and the corresponding source amount in rials, including zero amounts.
- **Payment schedules:** payment dates and associated amounts from recognized TSE Excel schedule sheets, retained separately from daily interest rows.

### Extraction Review Information

Payesh retains the extraction status, identified fields, missing required fields, processing time, and available error explanations. Spreadsheet review details also include the number of missing stored values when detected.

Field availability varies by source, document type, and layout. The list above describes supported extraction capabilities; it does not mean every announcement supplies every field. Required fields vary by document type, while other supported fields are optional.

## Collection and Review Workflow

1. A user selects **دریافت اطلاعیه‌ها**, or the configured update interval triggers a collection.
2. Payesh reads recent announcements from both sources and applies the source-specific rules.
3. New records are added; existing records are updated without creating duplicates for the same source identifier.
4. Missing attachments are downloaded, with failed downloads retried during later collections.
5. Supported files are processed into financial fields and daily interest rows.
6. The dashboard shows the results, original attachments, and any extraction gaps.

For TSE announcements, information from PDF and Excel attachments is combined. A field supplied by either file is
available at the announcement level; each attachment also retains its own extraction status and explanation.

## Information Quality and Transparency

Extraction is best effort and depends on the document layout and available text. **کامل** means the defined extraction
requirements were met; it does not certify the financial accuracy of the original document or every extracted value.

Incomplete results identify required fields that were not extracted. Additional explanations cover unsupported formats,
unreadable PDF text, missing spreadsheet values, and attachment failures. Optional fields do not determine completeness.

Excel processing reads stored values without recalculating formulas. Amounts are displayed in rials. Publication dates
are presented consistently in the Jalali calendar, and collection times are displayed in Tehran time.

Original documents remain accessible so users can confirm information before using it in their work. Existing stored
files were reprocessed when missing-field explanations were introduced.

## Operation and Deployment

The update interval defaults to **60 minutes** and can be changed or disabled. The data directory is configurable;
records and downloaded files persist in the selected database location. Startup configuration changes require a restart
and do not automatically move existing data.

Automatic collection works while the application is running. Closing the browser does not stop updates; stopping the
application or computer does. Collection starts after the configured interval, and overlapping web collection runs are
prevented.

Docker packaging and Compose configuration provide repeatable installation with persistent storage. The default Compose
dashboard address is **localhost:8001**. The Docker image was built successfully on Linux; Windows use through Docker
Desktop with Linux containers has not been verified on a Windows machine.

## Current Boundaries

- Coverage is limited to the current source pages. Announcements that leave those pages between updates can be missed.
- The application does not provide trading, investment recommendations, or financial calculations beyond reading
  supported source data.
- Some document layouts require manual review; OCR and universal document parsing are not implemented.
- Collection requires network access and depends on source availability and format stability.
- Deployment is intended for one local application process. User accounts, role-based access, and public hosting are
  outside the delivered scope.
- Persistent storage is provided; automated backups and automatic data migration between directories are not included.

## Delivery Outcome

Payesh now provides an operational workflow from recent announcement collection to document review, with scheduled
updates, clear extraction gaps, and persistent records. The repository includes contributor guidance, technical
operating instructions, and Docker packaging. Future expansion can build on this foundation through historical
collection, broader extraction coverage, or additional sources.
