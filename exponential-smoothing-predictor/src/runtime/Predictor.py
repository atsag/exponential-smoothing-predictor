# Copyright (c) 2023 Institute of Communication and Computer Systems
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.        

import datetime
import json
import threading
import time
import os, sys
import multiprocessing
import traceback
from subprocess import PIPE, run
from threading import Thread

from proton import Message

from exn import core
from jproperties import PropertyTuple, Properties
import logging
from exn import connector
from exn.core.handler import Handler
from exn.handler.connector_handler import ConnectorHandler
from runtime.operational_status.ApplicationState import ApplicationState
from runtime.predictions.Prediction import Prediction
from runtime.operational_status.EsPredictorState import EsPredictorState
from runtime.utilities.PredictionPublisher import PredictionPublisher
from runtime.utilities.Utilities import Utilities
print_with_time = Utilities.print_with_time

_logger = logging.getLogger(__name__)


def sanitize_prediction_statistics(prediction_confidence_interval, prediction_value, metric_name, lower_bound_value, upper_bound_value):

    print_with_time("Inside the sanitization process with an interval of  " + prediction_confidence_interval +" and a prediction of " + str(prediction_value))
    lower_value_prediction_confidence_interval = float(prediction_confidence_interval.split(",")[0])
    upper_value_prediction_confidence_interval = float(prediction_confidence_interval.split(",")[1])

    """if (not application_name in EsPredictorState.individual_application_state):
        print_with_time("There is an issue with the application name"+application_name+" not existing in individual application states")
        return prediction_confidence_interval,prediction_value_produced"""

    #lower_bound_value = application_state.lower_bound_value
    #upper_bound_value = application_state.upper_bound_value

    confidence_interval_modified = False
    new_prediction_confidence_interval = prediction_confidence_interval
    if ((lower_bound_value is None) and (upper_bound_value is None)):
        print_with_time(f"Lower value is unmodified - {lower_value_prediction_confidence_interval} and upper value is unmodified - {upper_value_prediction_confidence_interval}")
        return new_prediction_confidence_interval,prediction_value
    if (lower_bound_value is not None):
        if (upper_value_prediction_confidence_interval < lower_bound_value):
            upper_value_prediction_confidence_interval = lower_bound_value
            lower_value_prediction_confidence_interval = lower_bound_value
            confidence_interval_modified = True
        elif (lower_value_prediction_confidence_interval < lower_bound_value):
            lower_value_prediction_confidence_interval = lower_bound_value
            confidence_interval_modified = True
    if (upper_bound_value is not None):       
        if (lower_value_prediction_confidence_interval > upper_bound_value):
            lower_value_prediction_confidence_interval = upper_bound_value
            upper_value_prediction_confidence_interval = upper_bound_value
            confidence_interval_modified = True
        elif (upper_value_prediction_confidence_interval> upper_bound_value):
            upper_value_prediction_confidence_interval = upper_bound_value
            confidence_interval_modified = True
    
    if confidence_interval_modified:
        new_prediction_confidence_interval = str(lower_value_prediction_confidence_interval)+","+str(upper_value_prediction_confidence_interval)
        print_with_time("The confidence interval "+prediction_confidence_interval+" was modified, becoming "+str(new_prediction_confidence_interval)+", taking into account the values of the metric")
    if (prediction_value<lower_bound_value):
        print_with_time("The prediction value of " + str(prediction_value) + " for metric " + metric_name + " was sanitized to " + str(lower_bound_value))
        prediction_value = lower_bound_value
    elif (prediction_value > upper_bound_value):
        print_with_time("The prediction value of " + str(prediction_value) + " for metric " + metric_name + " was sanitized to " + str(upper_bound_value))
        prediction_value = upper_bound_value

    return new_prediction_confidence_interval,prediction_value


def predict_attribute(attribute,prediction_data_filename,lower_bound_value,upper_bound_value,next_prediction_time):

    prediction_confidence_interval_produced = False
    prediction_value_produced = False
    prediction_valid = False
    #os.chdir(os.path.dirname(configuration_file_location))
    

    from sys import platform
    if EsPredictorState.testing_prediction_functionality:
        print_with_time("Testing, so output will be based on the horizon setting from the properties file and the last timestamp in the data")
        print_with_time("Issuing command: Rscript forecasting_real_workload.R "+str(prediction_data_filename)+" "+attribute)

        # Windows
        if platform == "win32":
            command = ['Rscript', 'forecasting_real_workload.R', prediction_data_filename, attribute]
        # linux
        elif platform == "linux" or platform == "linux2":
            command = ["Rscript forecasting_real_workload.R "+str(prediction_data_filename) + " "+ str(attribute)]
        #Choosing the solution of linux
        else:
            command = ["Rscript forecasting_real_workload.R "+str(prediction_data_filename) + " "+ str(attribute)]
    else:
        print_with_time("The current directory is "+os.path.abspath(os.getcwd()))
        print_with_time("Issuing command: Rscript forecasting_real_workload.R "+str(prediction_data_filename)+" "+attribute+" "+next_prediction_time)

        # Windows
        if platform == "win32":
            command = ['Rscript', 'forecasting_real_workload.R', prediction_data_filename, attribute, next_prediction_time]
        # Linux
        elif platform == "linux" or platform == "linux2":
            command = ["Rscript forecasting_real_workload.R "+str(prediction_data_filename) + " "+ str(attribute)+" "+str(next_prediction_time) + " 2>&1"]
        #Choosing the solution of linux
        else:
            command = ["Rscript forecasting_real_workload.R "+str(prediction_data_filename) + " "+ str(attribute)+" "+str(next_prediction_time)]

    process_output = run(command, shell=True, stdout=PIPE, stderr=PIPE, universal_newlines=True)
    if (process_output.stdout==""):
        logging.error("Empty output from R predictions - the error output is the following:")
        print(process_output.stderr) #There was an error during the calculation of the predicted value

    process_output_string_list = process_output.stdout.replace("[1] ", "").replace("\"", "").split()
    prediction_value = 0
    prediction_confidence_interval = "-10000000000000000000000000,10000000000000000000000000"
    prediction_mae = 0
    prediction_mse = 0
    prediction_mape = 0
    prediction_smape = 0
    for string in process_output_string_list:
        if (string.startswith("Prediction:")):
            prediction_value = string.replace("Prediction:", "")
            prediction_value_produced = True
        if (string.startswith("Confidence_interval:")):
            prediction_confidence_interval = string.replace("Confidence_interval:", "")
            prediction_confidence_interval_produced = True
        elif (string.startswith("mae:")):
            prediction_mae = string.replace("mae:", "")
        elif (string.startswith("mse:")):
            prediction_mse = string.replace("mse:", "")
        elif (string.startswith("mape:")):
            prediction_mape = string.replace("mape:", "")
        elif (string.startswith("smape:")):
            prediction_smape = string.replace("smape:", "")
    if (prediction_confidence_interval_produced and prediction_value_produced):
        try:
            prediction_confidence_interval,prediction_value = sanitize_prediction_statistics(prediction_confidence_interval,float(prediction_value),attribute,lower_bound_value,upper_bound_value)
            prediction_valid = True
            print_with_time("The prediction for attribute " + attribute + " is " + str(prediction_value)+ " and the confidence interval is "+prediction_confidence_interval + " for prediction time "+str(next_prediction_time))
            _logger.info("The prediction for attribute " + attribute + " is " + str(prediction_value)+ " and the confidence interval is "+prediction_confidence_interval +  " for prediction time "+str(next_prediction_time))
        except Exception as e:
            logging.error(e)
    else:
        logging.error("There was an error during the calculation of the predicted value for "+str(attribute)+", the error log follows")
        logging.error(process_output.stdout)
        logging.error("\n")
        logging.error("----------------------")
        logging.error("Printing stderr")
        logging.error("----------------------")
        logging.error("\n")
        logging.error(process_output.stderr)
    
    output_prediction = Prediction(prediction_value, prediction_confidence_interval,prediction_valid,prediction_mae,prediction_mse,prediction_mape,prediction_smape)
    return output_prediction


def predict_attributes(application_state,next_prediction_time):
    attributes = application_state.metrics_to_predict
    pool = multiprocessing.Pool(len(attributes))
    print_with_time("Prediction thread pool size set to " + str(len(attributes)))
    prediction_results = {}
    attribute_predictions = {}

    for attribute in attributes:
        print_with_time("Starting " + attribute + " prediction thread")
        start_time = time.time()
        application_state.prediction_data_filename = application_state.get_prediction_data_filename(EsPredictorState.configuration_file_location,attribute)
        prediction_results[attribute] = pool.apply_async(predict_attribute, args=[attribute,application_state.prediction_data_filename, application_state.lower_bound_value[attribute],application_state.upper_bound_value[attribute],str(next_prediction_time)]
         )
        #attribute_predictions[attribute] = pool.apply_async(predict_attribute, args=[attribute, configuration_file_location,str(next_prediction_time)]).get()

    #for attribute in attributes:
    #    prediction_results[attribute].wait() #wait until the process is finished
    #pool.close()
    #pool.join()
    for attribute in attributes:
        attribute_predictions[attribute] = prediction_results[attribute].get() #get the results of the processing
        attribute_predictions[attribute].set_last_prediction_time_needed(int(time.time() - start_time))
        #prediction_time_needed[attribute])

    pool.close()
    pool.join()
    return attribute_predictions

def update_prediction_time(epoch_start,prediction_horizon,maximum_time_for_prediction):
    current_time = time.time()
    prediction_intervals_since_epoch = ((current_time - epoch_start)//prediction_horizon)
    estimated_time_after_prediction = current_time+maximum_time_for_prediction
    earliest_time_to_predict_at = epoch_start + (prediction_intervals_since_epoch+1)*prediction_horizon #these predictions will concern the next prediction interval

    if (estimated_time_after_prediction > earliest_time_to_predict_at ):
        future_prediction_time_factor = 1+(estimated_time_after_prediction-earliest_time_to_predict_at)//prediction_horizon
        prediction_time = earliest_time_to_predict_at+ future_prediction_time_factor*prediction_horizon
        print_with_time("Due to slowness of the prediction, skipping next time point for prediction (prediction at " + str(earliest_time_to_predict_at-prediction_horizon)+" for "+ str(earliest_time_to_predict_at)+") and targeting "+str(future_prediction_time_factor)+" intervals ahead (prediction at time point "+str(prediction_time-prediction_horizon)+" for "+ str(prediction_time)+")")
    else:
        prediction_time = earliest_time_to_predict_at + prediction_horizon
    print_with_time("Time is now "+str(current_time)+" and next prediction batch starts with prediction for time "+str(prediction_time))
    return prediction_time


def calculate_and_publish_predictions(application_state,maximum_time_required_for_prediction):
    start_forecasting = application_state.start_forecasting
    application_name = application_state.application_name
    while start_forecasting:
        print_with_time("Using " + EsPredictorState.configuration_file_location + f" for configuration details related to forecasts of {application_state.application_name}...")
        application_state.next_prediction_time = update_prediction_time(application_state.epoch_start, application_state.prediction_horizon,maximum_time_required_for_prediction)

        for attribute in application_state.metrics_to_predict:
            if ((application_state.previous_prediction is not None) and (application_state.previous_prediction[attribute] is not None) and (application_state.previous_prediction[attribute].last_prediction_time_needed>maximum_time_required_for_prediction)):
                maximum_time_required_for_prediction = application_state.previous_prediction[attribute].last_prediction_time_needed

        #Below we subtract one reconfiguration interval, as we cannot send a prediction for a time point later than one prediction_horizon interval
        wait_time = application_state.next_prediction_time - application_state.prediction_horizon - time.time()
        print_with_time("Waiting for "+str((int(wait_time*100))/100)+" seconds, until time "+datetime.datetime.fromtimestamp(application_state.next_prediction_time - application_state.prediction_horizon).strftime('%Y-%m-%d %H:%M:%S'))
        if (wait_time>0):
            time.sleep(wait_time)
            if(not start_forecasting):
                break

        Utilities.load_configuration()
        application_state.update_monitoring_data()
        first_prediction = None
        for prediction_index in range(0, EsPredictorState.total_time_intervals_to_predict):
            prediction_time = int(application_state.next_prediction_time)+prediction_index*application_state.prediction_horizon
            try:
                print_with_time ("Initiating predictions for all metrics for next_prediction_time, which is "+str(application_state.next_prediction_time))
                prediction = predict_attributes(application_state,prediction_time)
                if (prediction_time == int(application_state.next_prediction_time)):
                    first_prediction = prediction
            except Exception as e:
                print_with_time("Could not create a prediction for some or all of the metrics for time point " + str(application_state.next_prediction_time) +", proceeding to next prediction time. However, " + str(prediction_index) +" predictions were produced (out of the configured " + str(EsPredictorState.total_time_intervals_to_predict) + "). The encountered exception trace follows:")
                print(traceback.format_exc())
                #continue was here, to continue while loop, replaced by break
                break
            for attribute in application_state.metrics_to_predict:
                if(not prediction[attribute].prediction_valid):
                    #continue was here, to continue while loop, replaced by break
                    logging.warning(f"There was an invalid prediction for attribute {attribute}")
                    try:
                        logging.warning(f"The prediction value was {prediction[attribute].value} - breaking")
                    except Exception as e:
                        logging.error(str(e))
                        
                    continue
                if (EsPredictorState.disconnected or EsPredictorState.check_stale_connection()):
                    logging.info("Possible problem due to disconnection or a stale connection")
                    #State.connection.connect()
                message_not_sent = True
                current_time = int(time.time())
                prediction_message_body = {
                    "metricValue": float(prediction[attribute].value),
                    "level": 3,
                    "timestamp": current_time,
                    "probability": 0.95, #This is the default second parameter of the prediction intervals (first is 80%) created as part of the HoltWinters forecasting mode in R
                    "confidence_interval": [float(prediction[attribute].lower_confidence_interval_value) ,  float(
                        prediction[attribute].upper_confidence_interval_value)],
                    "predictionTime": prediction_time,
                }
                training_models_message_body = {
                    "metrics": application_state.metrics_to_predict,
                    "forecasting_method": "exponentialsmoothing",
                    "timestamp": current_time,
                }
                while (message_not_sent):
                    try:
                        #for publisher in State.broker_publishers:
                        #    if publisher.
                        for publisher in EsPredictorState.broker_publishers:
                            #if publisher.address=="eu.nebulouscloud.monitoring.preliminary_predicted.exponentialsmoothing"+attribute:

                            if publisher.key=="publisher_"+application_name+"-"+attribute:
                                publisher.send(prediction_message_body,application_name)


                        #State.connection.send_to_topic('intermediate_prediction.%s.%s' % (id, attribute), prediction_message_body)

                        #State.connection.send_to_topic('training_models',training_models_message_body)
                        message_not_sent = False
                        print_with_time("Successfully sent prediction message for "+str(attribute)+" to topic "+EsPredictorState.get_prediction_publishing_topic(attribute)+":\n\n%s\n\n" % (prediction_message_body))
                    except Exception as exception:
                        #State.connection.disconnect()
                        #State.connection = messaging.morphemic.Connection('admin', 'admin')
                        #State.connection.connect()
                        logging.error("Error sending intermediate prediction"+str(exception))
                        EsPredictorState.disconnected = False

        if (first_prediction is not None):
            application_state.previous_prediction = first_prediction #first_prediction is the first of the batch of the predictions which are produced. The size of this batch is set by the State.total_time_intervals_to_predict (currently set to 8)

        #State.number_of_days_to_use_data_from = (prediction_horizon - State.prediction_processing_time_safety_margin_seconds) / (wait_time / State.number_of_days_to_use_data_from)
        #State.number_of_days_to_use_data_from = 1 + int(
        #    (prediction_horizon - State.prediction_processing_time_safety_margin_seconds) /
        #    (wait_time / State.number_of_days_to_use_data_from)
        #)


#class Listener(messaging.listener.MorphemicListener):
class BootStrap(ConnectorHandler):
    def publish_live_status(self,context,liveness_probe_key):
        counter = 0
        while True:
            counter = counter+1
            if (counter%3600==1):
                print_with_time("Sending liveness probe "+str(counter))
            context.publishers[liveness_probe_key].send(body={
                'isalive': True
            })
            time.sleep(1)
    def ready (self, context):
        liveness_probe_key = 'exsmoothing_forecasting_eu.nebulouscloud.state.exponentialsmoothing.isalive'
        liveness_probe_publisher_exists = context.has_publisher(liveness_probe_key)
        
        if liveness_probe_publisher_exists:
            print_with_time("Starting to send liveness messages")            
        else:
            time.sleep(20)
            liveness_probe_publisher_exists = context.has_publisher('liveness_probe')
            if (not liveness_probe_publisher_exists):
                print_with_time('No liveness probe publisher exists. Exiting.')
                exit(-1)
        status_publishing_thread  = Thread(target=self.publish_live_status,args=[context,liveness_probe_key])
        status_publishing_thread.start()
    
class ConsumerHandler(Handler):

    def ready(self, context):
        
        if context.has_publisher('state'):
            context.publishers['state'].starting()
            context.publishers['state'].started()
            context.publishers['state'].custom('forecasting')
            context.publishers['state'].stopping()
            context.publishers['state'].stopped()

        print_with_time("Consumer handler ready")
            #context.publishers['publisher_cpu_usage'].send({
            #     'hello': 'world'
            #})

    def on_message(self, key, address, body, message: Message, context):
        address = address.replace("topic://"+EsPredictorState.GENERAL_TOPIC_PREFIX,"")
        if (address).startswith(EsPredictorState.MONITORING_DATA_PREFIX):
            address = address.replace(EsPredictorState.MONITORING_DATA_PREFIX, "", 1)
        
            logging.debug("New monitoring data arrived at topic "+address)

            if address == 'metric_list':

                application_name = body["name"]
                message_version = body["version"]
                application_state = None
                individual_application_state = {}
                application_already_defined = application_name in EsPredictorState.individual_application_state
                if ( application_already_defined and
                   ( message_version == EsPredictorState.individual_application_state[application_name].message_version )
                ):
                    individual_application_state = EsPredictorState.individual_application_state
                    application_state = individual_application_state[application_name]

                    print_with_time("Using existing application definition for "+application_name)
                else:
                    if (application_already_defined):
                        print_with_time("Updating application "+application_name+" based on new metrics list message")
                    else:
                        print_with_time("Creating new application "+application_name)
                    application_state = ApplicationState(application_name,message_version)
                metric_list_object = body["metric_list"]
                lower_bound_value = application_state.lower_bound_value
                upper_bound_value = application_state.upper_bound_value
                for metric_object in metric_list_object:
                    lower_bound_value[metric_object["name"]]=float(metric_object["lower_bound"])
                    upper_bound_value[metric_object["name"]]=float(metric_object["upper_bound"])

                    application_state.lower_bound_value.update(lower_bound_value)
                    application_state.upper_bound_value.update(upper_bound_value)

                application_state.initial_metric_list_received = True

                individual_application_state[application_name] = application_state
                EsPredictorState.individual_application_state.update(individual_application_state)
                #body = json.loads(body)
                #for element in body:
                #    State.metrics_to_predict.append(element["metric"])


        elif (address).startswith(EsPredictorState.FORECASTING_CONTROL_PREFIX):
            address = address.replace(EsPredictorState.FORECASTING_CONTROL_PREFIX, "", 1)
            logging.info("The address is " + address)


            if address == 'test.exponentialsmoothing':
                EsPredictorState.testing_prediction_functionality = True

            elif address == 'start_forecasting.exponentialsmoothing':
                try:
                    application_name = body["name"]
                    message_version = 0
                    if (not "version" in body):
                        logging.debug("There was an issue in finding the message version in the body of the start forecasting message, assuming it is 1")
                        message_version = 1
                    else:
                        message_version = body["version"]
                    if (application_name in EsPredictorState.individual_application_state) and (message_version <= EsPredictorState.individual_application_state[application_name].message_version):
                        application_state = EsPredictorState.individual_application_state[application_name]
                    else:
                        EsPredictorState.individual_application_state[application_name] = ApplicationState(application_name,message_version)
                        application_state = EsPredictorState.individual_application_state[application_name]

                    if (not application_state.start_forecasting) or ((application_state.metrics_to_predict is not None) and (set(application_state.metrics_to_predict)!=set(body["metrics"]))):
                        application_state.metrics_to_predict = body["metrics"]
                        print_with_time("Received request to start predicting the following metrics: "+ ",".join(application_state.metrics_to_predict)+" for application "+application_name+", proceeding with the prediction process")
                        if (not application_state.start_forecasting):
                            #Coarse initialization, needs to be improved with metric_list message
                            for metric in application_state.metrics_to_predict:
                                if (metric not in application_state.lower_bound_value and metric not in application_state.upper_bound_value):
                                    application_state.lower_bound_value[metric] = None
                                    application_state.upper_bound_value[metric] = None
                        else:
                            new_metrics = set(body["metrics"]) - set(application_state.metrics_to_predict)
                            for metric in new_metrics:
                                if (metric not in application_state.lower_bound_value and metric not in application_state.upper_bound_value):
                                    application_state.lower_bound_value[metric] = None
                                    application_state.upper_bound_value[metric] = None
                    else:
                        application_state.metrics_to_predict = body["metrics"]
                        print_with_time("Received request to start predicting the following metrics: "+ str(body["metrics"])+" for application "+application_name+"but it was perceived as a duplicate")
                        return
                    application_state.broker_publishers = []
                    for metric in application_state.metrics_to_predict:
                        EsPredictorState.broker_publishers.append (PredictionPublisher(application_name,metric))
                    EsPredictorState.publishing_connector = connector.EXN('publishing_'+EsPredictorState.forecaster_name+'-'+application_name, handler=BootStrap(),  #consumers=list(State.broker_consumers),
                        consumers=[],
                        publishers=EsPredictorState.broker_publishers,
                        url=EsPredictorState.broker_address,
                        port=EsPredictorState.broker_port,
                        username=EsPredictorState.broker_username,
                        password=EsPredictorState.broker_password
                    )
                    #EsPredictorState.publishing_connector.start()
                    thread = threading.Thread(target=EsPredictorState.publishing_connector.start, args=())
                    thread.start()

                except Exception as e:
                    print_with_time("Could not load json object to process the start forecasting message \n"+str(body))
                    print(traceback.format_exc())
                    return

                #if (not State.initial_metric_list_received):
                #    print_with_time("The initial metric list has not been received,
                #therefore no predictions are generated")
                #    return

                try:
                    application_state = EsPredictorState.individual_application_state[application_name]
                    application_state.start_forecasting = True
                    application_state.epoch_start = body["epoch_start"]
                    application_state.prediction_horizon = int(body["prediction_horizon"])
                    application_state.next_prediction_time = update_prediction_time(application_state.epoch_start,application_state.prediction_horizon,EsPredictorState.prediction_processing_time_safety_margin_seconds) # State.next_prediction_time was assigned the value of State.epoch_start here, but this re-initializes targeted prediction times after each start_forecasting message, which is not desired necessarily
                    print_with_time("A start_forecasting message has been received, epoch start and prediction horizon are "+str(application_state.epoch_start)+", and "+str(application_state.prediction_horizon)+ " seconds respectively")
                except Exception as e:
                    print_with_time("Problem while retrieving epoch start and/or prediction_horizon")
                    print(traceback.format_exc())
                    return

                with open(EsPredictorState.configuration_file_location, "r+b") as f:

                    configuration = Properties()
                    configuration.load(f, "utf-8") 
                    initial_seconds_aggregation_value = int(configuration.get("number_of_seconds_to_aggregate_on").data)

                    if (application_state.prediction_horizon<initial_seconds_aggregation_value):
                        print_with_time("Changing number_of_seconds_to_aggregate_on to "+str(application_state.prediction_horizon)+" from its initial value "+str(initial_seconds_aggregation_value))
                        configuration.set("number_of_seconds_to_aggregate_on", str(application_state.prediction_horizon))

                    f.seek(0)
                    f.truncate(0)
                    configuration.store(f, encoding="utf-8")


                maximum_time_required_for_prediction = EsPredictorState.prediction_processing_time_safety_margin_seconds #initialization, assuming X seconds processing time to derive a first prediction
                if ((EsPredictorState.individual_application_state[application_name].prediction_thread is None) or (not EsPredictorState.individual_application_state[application_name].prediction_thread.is_alive())):
                    EsPredictorState.individual_application_state[application_name].prediction_thread = threading.Thread(target = calculate_and_publish_predictions, args =[application_state,maximum_time_required_for_prediction])
                    EsPredictorState.individual_application_state[application_name].prediction_thread.start()

                #waitfor(first period)

            elif address == 'stop_forecasting.exponentialsmoothing':
                #waitfor(first period)
                application_name = body["name"]
                application_state = EsPredictorState.individual_application_state[application_name]
                print_with_time("Received message to stop predicting some of the metrics")
                metrics_to_remove = body["metrics"] 
                for metric in metrics_to_remove:
                    if (application_state.metrics_to_predict.__contains__(metric)):
                        print_with_time("Stopping generating predictions for metric "+metric)
                        application_state.metrics_to_predict.remove(metric)
                if (len(metrics_to_remove)==0 or len(application_state.metrics_to_predict)==0):
                    EsPredictorState.individual_application_state[application_name].start_forecasting = False
                    EsPredictorState[application_name].prediction_thread.join()

            else:
                print_with_time("The address was "+ address +" and did not match metrics_to_predict/test.exponentialsmoothing/start_forecasting.exponentialsmoothing/stop_forecasting.exponentialsmoothing")
                #        logging.info(f"Received {key} => {address}")
        
        elif (address).startswith(EsPredictorState.COMPONENT_STATE_PREFIX):
        
            import os      
            # Specify the directory and filename
            from pathlib import Path
            directory = "/home/r_predictions"
            Path(directory).mkdir(parents=True, exist_ok=True)
            filename = "is_alive.txt"
            
            # Create the file
            with open(os.path.join(directory, filename), "w") as f:
                current_message = f"Liveness probe received at {address}"
                #current_message = print_with_time(f"Liveness probe received at {address}")
                f.write(current_message)        

        else:
            print_with_time("Received message "+body+" but could not handle it")
def get_dataset_file(attribute):
    pass

def main():

    #Change to the appropriate directory in order i) To invoke the forecasting script appropriately and ii) To store the monitoring data necessary for predictions
    from sys import platform
    if platform == "win32" or bool(os.environ.get("TEST_RUN",False)):
        print(os.listdir("."))
        os.chdir("../r_predictors")
        # linux
    elif platform == "linux" or platform == "linux2":
        os.chdir("/home/r_predictions")
    else:
        os.chdir("/home/r_predictions")

    EsPredictorState.configuration_file_location = sys.argv[1]
    Utilities.load_configuration()
    Utilities.update_influxdb_organization_id()
# Subscribe to retrieve the metrics which should be used

    logging.basicConfig(level=logging.INFO)
    id = "exponentialsmoothing"
    EsPredictorState.disconnected = True

    #while(True):
    #    State.connection = messaging.morphemic.Connection('admin', 'admin')
    #    State.connection.connect()
    #    State.connection.set_listener(id, Listener())
    #    State.connection.topic("test","helloid")
    #    State.connection.send_to_topic("test","HELLO!!!")
    #exit(100)

    while True:
        topics_to_subscribe = ["eu.nebulouscloud.monitoring.metric_list","eu.nebulouscloud.monitoring.realtime.>","eu.nebulouscloud.forecasting.start_forecasting.exponentialsmoothing","eu.nebulouscloud.forecasting.stop_forecasting.exponentialsmoothing",
          "eu.nebulouscloud.state.exponentialsmoothing.isalive"]
        
        topics_to_publish = ["eu.nebulouscloud.state.exponentialsmoothing.isalive"]

        current_consumers = []
        current_publishers = []

        for topic in topics_to_subscribe:
            current_consumer = core.consumer.Consumer(key='exsmoothing_forecasting_'+topic,address=topic,handler=ConsumerHandler(), topic=True,fqdn=True)
            EsPredictorState.broker_consumers.append(current_consumer)
            current_consumers.append(current_consumer)
            
        for topic in topics_to_publish:
            current_publisher = core.publisher.Publisher(key='exsmoothing_forecasting_'+topic,address=topic, topic=True,fqdn=True)
            EsPredictorState.broker_publishers.append(current_publisher)
            current_publishers.append(current_publisher)
            
        EsPredictorState.subscribing_connector = connector.EXN(EsPredictorState.forecaster_name, handler=BootStrap(),
                                                               #consumers=list(State.broker_consumers),
                                                               consumers=EsPredictorState.broker_consumers,
                                                               publishers=EsPredictorState.broker_publishers,
                                                               url=EsPredictorState.broker_address,
                                                               port=EsPredictorState.broker_port,
                                                               username=EsPredictorState.broker_username,
                                                               password=EsPredictorState.broker_password
                                                               )


        #connector.start()
        thread = threading.Thread(target=EsPredictorState.subscribing_connector.start, args=())
        thread.start()
        EsPredictorState.disconnected = False;

        print_with_time("Checking (EMS) broker connectivity state, possibly ready to start")
        if (EsPredictorState.disconnected or EsPredictorState.check_stale_connection()):
            try:
                #State.connection.disconnect() #required to avoid the already connected exception
                #State.connection.connect()
                EsPredictorState.disconnected = True
                print_with_time("Possible problem in the connection")
            except Exception as e:
                print_with_time("Encountered exception while trying to connect to broker")
                print(traceback.format_exc())
                EsPredictorState.disconnected = True
                time.sleep(5)
                continue
        EsPredictorState.disconnection_handler.acquire()
        EsPredictorState.disconnection_handler.wait()
        EsPredictorState.disconnection_handler.release()

    #State.connector.stop()

if __name__ == "__main__":
    main()