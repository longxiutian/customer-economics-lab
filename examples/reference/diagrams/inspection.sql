CREATE VIEW people AS SELECT * FROM read_csv_auto('C:/Users/longxiu/Documents/ChatGPT/customer-economics-lab/data/people.csv', header=true);

CREATE VIEW subscription_periods AS SELECT * FROM read_csv_auto('C:/Users/longxiu/Documents/ChatGPT/customer-economics-lab/data/subscription_periods.csv', header=true);

CREATE VIEW transactions AS SELECT * FROM read_csv_auto('C:/Users/longxiu/Documents/ChatGPT/customer-economics-lab/data/transactions.csv', header=true);

CREATE VIEW product_events AS SELECT * FROM read_csv_auto('C:/Users/longxiu/Documents/ChatGPT/customer-economics-lab/data/product_events.csv', header=true);

CREATE VIEW feedback AS SELECT * FROM read_csv_auto('C:/Users/longxiu/Documents/ChatGPT/customer-economics-lab/data/feedback.csv', header=true);

CREATE VIEW campaign_spend AS SELECT * FROM read_csv_auto('C:/Users/longxiu/Documents/ChatGPT/customer-economics-lab/data/campaign_spend.csv', header=true);

CREATE VIEW acquisition_attribution AS SELECT * FROM read_csv_auto('C:/Users/longxiu/Documents/ChatGPT/customer-economics-lab/data/acquisition_attribution.csv', header=true);

CREATE VIEW experiment_assignments AS SELECT * FROM read_csv_auto('C:/Users/longxiu/Documents/ChatGPT/customer-economics-lab/data/experiment_assignments.csv', header=true);

SELECT count(*) FROM people;

SELECT count(*) FROM subscription_periods;

SELECT count(*) FROM transactions;

SELECT count(*) FROM product_events;

SELECT count(*) FROM feedback;

SELECT count(*) FROM campaign_spend;

SELECT count(*) FROM acquisition_attribution;

SELECT count(*) FROM experiment_assignments;
